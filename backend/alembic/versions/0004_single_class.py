"""Single student enrollment, leave/removal metadata and unverified display fallback."""
from alembic import op
import sqlalchemy as sa
revision = '0004_single_class'
down_revision = '0003_operator_identity'
branch_labels = depends_on = None


def upgrade():
    # Fail transactionally rather than silently evicting existing students.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT m.user_id FROM class_memberships m JOIN users u ON u.id=m.user_id
                 WHERE m.active AND u.role='student' GROUP BY m.user_id HAVING count(*)>1)
      THEN RAISE EXCEPTION 'Multiple active student memberships: resolve before migration 0004'; END IF;
    END $$""")
    op.add_column('classes', sa.Column('enrollment_open', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('class_memberships', sa.Column('left_at', sa.Float(), nullable=True))
    op.add_column('class_memberships', sa.Column('removed_at', sa.Float(), nullable=True))
    # Historical inactive memberships had no voluntary-leave flow: treat them as removed.
    op.execute('UPDATE class_memberships SET removed_at=0 WHERE NOT active')
    op.execute("UPDATE class_memberships SET role=CASE WHEN users.role='ta' THEN 'ta' ELSE 'teacher' END FROM users WHERE users.id=class_memberships.user_id AND users.role<>'student' AND class_memberships.role='student'")
    op.execute("UPDATE class_memberships SET role='student' FROM users WHERE users.id=class_memberships.user_id AND users.role='student'")
    op.create_index('uq_one_active_class_per_student', 'class_memberships', ['user_id'], unique=True,
                    postgresql_where=sa.text("role = 'student' AND active"))
    # Maintain the indexed role even for SQL/CLI role updates outside HTTP routes.
    op.execute("""CREATE FUNCTION fogwrite_membership_role() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE account_role text;
    BEGIN
      SELECT role INTO account_role FROM users WHERE id=NEW.user_id FOR UPDATE;
      IF account_role='student' THEN NEW.role='student';
      ELSIF NEW.role='student' THEN NEW.role=CASE WHEN account_role='ta' THEN 'ta' ELSE 'teacher' END;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER trg_membership_role BEFORE INSERT OR UPDATE OF user_id, role, active ON class_memberships FOR EACH ROW EXECUTE FUNCTION fogwrite_membership_role()")
    op.execute("""CREATE FUNCTION fogwrite_user_role() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.role IS DISTINCT FROM OLD.role THEN
        IF NEW.role='student' THEN
          UPDATE class_memberships SET role='student' WHERE user_id=NEW.id;
        ELSE
          UPDATE class_memberships SET role=CASE WHEN NEW.role='ta' THEN 'ta' ELSE 'teacher' END WHERE user_id=NEW.id AND role='student';
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    # AFTER: membership trigger must read the newly stored authoritative role.
    op.execute("CREATE TRIGGER trg_user_membership_role AFTER UPDATE OF role ON users FOR EACH ROW EXECUTE FUNCTION fogwrite_user_role()")
    op.add_column('users', sa.Column('reported_full_name', sa.String(120), nullable=True))
    op.add_column('users', sa.Column('reported_email', sa.String(254), nullable=True))


def downgrade():
    op.execute('DROP TRIGGER trg_user_membership_role ON users')
    op.execute('DROP TRIGGER trg_membership_role ON class_memberships')
    op.execute('DROP FUNCTION fogwrite_user_role()')
    op.execute('DROP FUNCTION fogwrite_membership_role()')
    op.drop_column('users', 'reported_email')
    op.drop_column('users', 'reported_full_name')
    op.drop_index('uq_one_active_class_per_student', table_name='class_memberships')
    op.drop_column('class_memberships', 'removed_at')
    op.drop_column('class_memberships', 'left_at')
    op.drop_column('classes', 'enrollment_open')
