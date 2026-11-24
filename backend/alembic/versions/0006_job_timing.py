"""Persist first worker start; historical timing remains unknown."""
from alembic import op
import sqlalchemy as sa
revision = '0006_job_timing'
down_revision = '0005_content_cache'
branch_labels = depends_on = None
def upgrade():
    op.add_column('jobs', sa.Column('first_started_at', sa.Float(), nullable=True))
def downgrade():
    op.drop_column('jobs', 'first_started_at')
