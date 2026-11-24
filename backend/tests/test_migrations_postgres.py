"""Real upgrade path in a disposable schema; never resets application tables."""
import asyncio
import json
import os
import subprocess
import sys
from uuid import uuid4
from pathlib import Path
import pytest


def test_postgres_legacy_upgrade():
    url=os.getenv('MIGRATION_TEST_DATABASE_URL')
    if not url:
        pytest.skip('MIGRATION_TEST_DATABASE_URL not provided')
    import asyncpg
    schema='migration_test_'+uuid4().hex
    plain=url.replace('postgresql+asyncpg://','postgresql://')
    async def sql(query):
        conn=await asyncpg.connect(plain)
        try:
            await conn.execute('SET search_path TO '+schema)
            if query.lstrip().upper().startswith('SELECT'): return await conn.fetch(query)
            await conn.execute(query)
            return []
        finally: await conn.close()
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'APP_ENV':'test','MIGRATION_DATABASE_URL':url,'FOGWRITE_MIGRATION_TEST_SCHEMA':schema}
    def migrate(*args):
        result=subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini',*args],cwd=root,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
    asyncio.run(sql('CREATE SCHEMA '+schema))
    try:
        migrate('upgrade','0003_operator_identity')
        asyncio.run(sql("""
        INSERT INTO users(id,external_auth_id,role,active,created_at,bonus_daily_credits) VALUES ('u','legacy-user','student',true,1,0);
        INSERT INTO classes(id,name,teacher_id,invite_hash,invite_expires_at,invite_max_uses,invite_uses,active,created_at,daily_student_quota) VALUES ('c','Legacy','u','hash',1,10,0,true,1,3);
        INSERT INTO class_memberships(id,class_id,user_id,role,active,joined_at) VALUES ('m','c','u','student',false,1);
        INSERT INTO submissions(id,user_id,class_id,prompt,essay,word_count,warnings,status,config_snapshot,created_at) VALUES ('s','u','c','question','legacy essay',2,'[]','COMPLETED','{}',1);
        INSERT INTO practice_sets(submission_id,state,payload,templates,draft_answers) VALUES ('s','ready','{"exercises":[{"exercise_id":"legacy-ex"}]}','[]','[]');
        """))
        migrate('upgrade','head')
        migrate('check')
        rows=asyncio.run(sql("SELECT essay, content_hash, config_snapshot FROM submissions WHERE id='s'"))
        assert rows[0]['essay']=='legacy essay' and rows[0]['content_hash'] is None
        assert json.loads(rows[0]['config_snapshot'])=={}
        assert asyncio.run(sql("SELECT submission_id FROM practice_exercises WHERE exercise_id='legacy-ex'"))[0]['submission_id']=='s'
        assert asyncio.run(sql("SELECT removed_at FROM class_memberships WHERE id='m'"))[0]['removed_at']==0
        names={r['trigger_name'] for r in asyncio.run(sql("SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema=current_schema()"))}
        assert {'trg_membership_role','trg_user_membership_role'} <= names
        assert asyncio.run(sql("SELECT count(*) n FROM submission_requests"))[0]['n']==0
        indexes={r['indexname'] for r in asyncio.run(sql("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema()"))}
        assert {'uq_one_active_class_per_student','ix_submissions_content_hash','ix_practice_exercises_submission_id'} <= indexes
        assert 'first_started_at' in {r['column_name'] for r in asyncio.run(sql("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='jobs'"))}
    finally:
        asyncio.run(sql('DROP SCHEMA '+schema+' CASCADE'))
