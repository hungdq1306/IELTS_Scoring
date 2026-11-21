"""SQLite is a deterministic adapter; production lock claims require isolated Postgres."""
import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
import pytest
from sqlalchemy import select, update
from app.models import User, Membership, Submission, SystemSetting
from app.entitlements import vn_day, get_user_quota_status
from app.grading.v2 import AssessmentOutputV2, essay_metadata
from app.grading.schemas import CRITERIA, Scores
from app.grading.task2 import overall_band
from app.services.scorer import calibrate, baseline_config, score
from app.providers.base import Generation
from test_concurrency_and_guardrails import application, headers, submit, ESSAY, QUESTION
from test_mvp import payload


def test_unenrolled_join_three_credits_refund_and_rotation(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            async with c.database.transaction() as db:
                await db.execute(update(Membership).where(Membership.user_id==c.accounts[0].id).values(active=False))
            q=await c.client.get('/api/me/quota',headers=headers())
            assert q.json()['daily_limit']==0
            denied=await submit(c)
            assert denied.status_code==403 and denied.json()['detail']['code']=='CLASS_ENROLLMENT_REQUIRED'
            room=await c.client.post('/api/teacher/classes',headers=headers(subject='user_teacher'),json={'name':'V2'})
            code=room.json()['join_code']; rid=room.json()['id']
            assert len(code)==8 and not set('01OI')&set(code)
            joined=await c.client.post('/api/classes/join',headers=headers(),json={'join_code':' '+code.lower()+' '})
            assert joined.status_code==200 and joined.json()['quota_status']['remaining_today']==3
            assert 'join_code' not in (await c.client.get('/api/auth/me',headers=headers())).text
            responses=await asyncio.gather(*(submit(c,key='v2_request_'+str(i)) for i in range(4)))
            assert [r.status_code for r in responses].count(202)==3
            assert [r.status_code for r in responses].count(429)==1
            from app.queue import claim
            from app.worker import Worker
            from app.providers.base import ProviderError
            from test_concurrency_and_guardrails import FakeProvider
            job=await claim(c.database,c.settings)
            worker=Worker(c.database,c.settings,FakeProvider(),FakeProvider())
            assert await worker.finish(job,error=ProviderError('permanent_failure','Fixture',503,False))
            assert (await c.client.get('/api/me/quota',headers=headers())).json()['remaining_today']==1
            rotated=await c.client.post('/api/teacher/classes/'+rid+'/rotate-code',headers=headers(subject='user_teacher'))
            assert rotated.status_code==200 and rotated.json()['join_code']!=code
            assert (await c.client.post('/api/classes/join',headers=headers(1),json={'join_code':code})).status_code==400
            assert (await c.client.get('/api/teacher/classes/'+rid+'/students',headers=headers(subject='user_other_teacher'))).status_code==404
            teacher=(await c.client.get('/api/me/quota',headers=headers(subject='user_teacher'))).json()
            assert teacher['daily_limit']==20
            assert (await c.client.get('/api/me/quota',headers=headers(subject='user_ta'))).json()['daily_limit']==5
            ta_rooms=(await c.client.get('/api/teacher/classes',headers=headers(subject='user_ta'))).json()['items']
            assert all('join_code' not in room for room in ta_rooms)
            async with c.database.transaction() as db:
                teacher=await db.scalar(select(User).where(User.external_auth_id=='user_teacher'))
                teacher.role='ta'
            assert (await c.client.post('/api/teacher/classes/'+rid+'/rotate-code',headers=headers(subject='user_teacher'))).status_code==404
    asyncio.run(scenario())


def test_admin_governance_scope_and_global_cap(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            async with c.database.transaction() as db:
                owner=await db.scalar(select(User).where(User.external_auth_id=='user_teacher'));owner.role='admin'; aid=owner.id
            admin=headers(subject='user_teacher')
            assert (await c.client.get('/api/admin/users',headers=headers())).status_code==403
            changed=await c.client.patch('/api/admin/users/'+c.accounts[0].id,headers=admin,json={'role':'teacher','bonus_daily_credits':2})
            assert changed.status_code==200
            assert (await c.client.get('/api/me/quota',headers=headers())).json()['daily_limit']==22
            assert (await c.client.patch('/api/admin/users/'+aid,headers=admin,json={'role':'student'})).status_code==409
            patch=await c.client.patch('/api/admin/settings',headers=admin,json={'global_daily_submission_cap':1,'calibration_offsets_json':{'tr':0.5}})
            assert patch.status_code==200
            assert (await submit(c,key='global_first')).status_code==202
            blocked=await submit(c,1,key='global_second')
            assert blocked.status_code==429 and blocked.json()['detail']['code']=='GLOBAL_DAILY_CAP'
            stats=(await c.client.get('/api/admin/overview',headers=admin)).json()
            assert stats['today_submissions']==1 and stats['queue_depth']==1
            assert stats['users_by_role']['admin']==1
            assert (await c.client.patch('/api/admin/settings',headers=admin,json={'calibration_offsets_json':{'tr':2.5}})).status_code==422
    asyncio.run(scenario())


def test_vietnam_midnight_telemetry_and_rounding():
    before=datetime.fromisoformat('2026-11-20T23:59:59+07:00').timestamp()
    after=before+1
    assert vn_day(after)[0]-vn_day(before)[0]==86400
    metadata=essay_metadata('Same repeated text. Same repeated text.\n\nNew paragraph here.')
    assert metadata['paragraph_count']==2 and metadata['ngram_repetition_ratio']['2']>0
    assert sum(metadata['words_per_paragraph'])==metadata['word_count']
    assert next(iter(AssessmentOutputV2.model_fields))=='structural_audit'
    for raw,expected in ((6.25,6.5),(6.75,7.0)):
        scores=Scores(**dict(zip(CRITERIA,[raw-.25,raw-.25,raw+.25,raw+.25])))
        assert overall_band(scores)==expected
    assert calibrate(dict.fromkeys(CRITERIA,8.5),dict.fromkeys(CRITERIA,1)).task_response==9


def v2_output():
    p=payload()
    return dict(structural_audit=dict(prompt_subtasks_addressed=['Full: transport improvements.'],paragraph_core_claims=['Improve public transport.'],circular_or_padding_flags=[],cohesion_faults=[]),
        tr_reasoning='The task is addressed.',tr_score=6.5,cc_reasoning='Ideas progress.',cc_score=6.5,
        lr_reasoning='Appropriate vocabulary.',lr_score=6.5,gra_reasoning='Mixed structures.',gra_score=6.5,
        criterion_feedback=p['criterion_feedback'],sentence_annotations=[],top_weaknesses=p['priority_improvements'],
        grammar_corrections=[],aspect_reviews=[],paragraph_reviews=[],language_suggestions=[])


def test_v2_schema_rejects_invalid_bands_and_preserves_audit_order():
    from pydantic import ValidationError
    from app.providers.gemini import gemini_schema
    valid = v2_output()
    assert AssessmentOutputV2.model_validate(valid).tr_score == 6.5
    assert next(iter(gemini_schema(AssessmentOutputV2)['properties'])) == 'structural_audit'
    for value in (6.1, 9.5, -0.5):
        with pytest.raises(ValidationError): AssessmentOutputV2.model_validate({**valid,'tr_score':value})


def test_v2_scorer_adapter_metadata_and_calibration():
    class Provider:
        async def generate_structured(self,system,user,schema):
            assert schema is AssessmentOutputV2 and '<essay_metadata>' in user and '<student_essay>' in user
            assert 'ANTI LENGTH BIAS' in system
            return Generation(json.dumps(v2_output()),'fixture',None,1,{'total_token_count':20},[])
    async def scenario():
        submission=SimpleNamespace(prompt=QUESTION,essay=ESSAY,warnings=[],config_snapshot={'fewshot':baseline_config(),'prompt_version':'v2','global_offsets':{'tr':.5}})
        result=await score(submission,Provider())
        assert result['criterion_scores']['task_response']==7
        assert result['raw_criterion_scores']['task_response']==6.5
        assert result['prompt_version'].startswith('v2:') and result['structural_audit']
    asyncio.run(scenario())
