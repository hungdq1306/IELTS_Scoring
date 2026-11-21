"""Add verified identity cache without changing pilot data."""
from alembic import op
import sqlalchemy as sa
revision = '0003_operator_identity'
down_revision = '0002_rbac_v2'
branch_labels = depends_on = None

def upgrade():
    for name,length in [('full_name',200),('email',320),('avatar_url',2000)]:
        op.add_column('users',sa.Column(name,sa.String(length),nullable=True))
    op.add_column('users',sa.Column('profile_synced_at',sa.Float(),nullable=True))
    op.add_column('submissions',sa.Column('credit_reserved_at',sa.Float(),nullable=True))

def downgrade():
    op.drop_column('submissions','credit_reserved_at')
    for name in ['profile_synced_at','avatar_url','email','full_name']:op.drop_column('users',name)
