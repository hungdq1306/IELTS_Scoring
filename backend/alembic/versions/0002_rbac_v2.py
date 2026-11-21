"""Calendar quotas, private retrievable invites and system settings."""
from alembic import op
import sqlalchemy as sa

revision = '0002_rbac_v2'
down_revision = '0001_pilot'
branch_labels = depends_on = None


def upgrade():
    op.add_column('users', sa.Column('bonus_daily_credits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('classes', sa.Column('join_code', sa.String(40), nullable=True))
    op.create_index('ix_classes_join_code', 'classes', ['join_code'], unique=True)
    op.add_column('classes', sa.Column('daily_student_quota', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('class_memberships', sa.Column('joined_at', sa.Float(), nullable=False, server_default='0'))
    op.create_table('system_settings', sa.Column('key', sa.String(100), primary_key=True), sa.Column('value', sa.JSON(), nullable=False))
    op.create_table('provider_usage', sa.Column('id',sa.String(36),primary_key=True), sa.Column('model',sa.String(120),nullable=False),
                    sa.Column('usage',sa.JSON(),nullable=False),sa.Column('outcome',sa.String(40),nullable=False),sa.Column('created_at',sa.Float(),nullable=False))


def downgrade():
    op.drop_table('provider_usage')
    op.drop_table('system_settings')
    op.drop_column('class_memberships', 'joined_at')
    op.drop_column('classes', 'daily_student_quota')
    op.drop_index('ix_classes_join_code', table_name='classes')
    op.drop_column('classes', 'join_code')
    op.drop_column('users', 'bonus_daily_credits')
