"""Grading-context cache and direct exercise ownership lookup."""
from alembic import op
import sqlalchemy as sa

revision = '0005_content_cache'
down_revision = '0004_single_class'
branch_labels = depends_on = None


def upgrade():
    # Historical rows intentionally remain null: their model/context may be unknown.
    op.add_column('submissions', sa.Column('content_hash', sa.String(64), nullable=True))
    op.create_index('ix_submissions_content_hash', 'submissions', ['content_hash'])
    op.create_table('submission_requests',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('request_key', sa.String(100), primary_key=True),
        sa.Column('submission_id', sa.String(36), sa.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('reused', sa.Boolean(), nullable=False))
    op.create_index('ix_submission_requests_submission_id', 'submission_requests', ['submission_id'])
    op.create_table('practice_exercises',
        sa.Column('exercise_id', sa.String(80), primary_key=True),
        sa.Column('submission_id', sa.String(36), sa.ForeignKey('practice_sets.submission_id', ondelete='CASCADE'), nullable=False))
    op.create_index('ix_practice_exercises_submission_id', 'practice_exercises', ['submission_id'])
    op.execute("""INSERT INTO practice_exercises (exercise_id, submission_id)
        SELECT item->>'exercise_id', p.submission_id FROM practice_sets p
        CROSS JOIN LATERAL json_array_elements(COALESCE(p.payload::json->'exercises', '[]'::json)) item
        WHERE p.state='ready' AND item->>'exercise_id' IS NOT NULL""")


def downgrade():
    op.drop_table('practice_exercises')
    op.drop_table('submission_requests')
    op.drop_index('ix_submissions_content_hash', table_name='submissions')
    op.drop_column('submissions', 'content_hash')
