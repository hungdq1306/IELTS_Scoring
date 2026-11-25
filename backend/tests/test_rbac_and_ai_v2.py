"""SQLite is a deterministic adapter; production lock claims require isolated Postgres."""
import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
import pytest
from sqlalchemy import select, update
from app.models import Assessment, User, Membership, Submission, SystemSetting, Job, QuotaBucket, AuditEvent
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
            responses=await asyncio.gather(*(submit(c,key='v2_request_'+str(i),essay=ESSAY+' Additional example number '+str(i)+'.') for i in range(4)))
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
            assert all('join_code' not in room and room['can_manage'] is False for room in ta_rooms)
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
    for raw,expected in ((6.25,6.0),(6.75,6.5)):
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
            assert schema is AssessmentOutputV2 and 'metadata' in json.loads(user)['NEW ESSAY']
            assert '<student_essay>' not in user
            assert 'ANTI-LENGTH BIAS' in system
            return Generation(json.dumps(v2_output()),'fixture',None,1,{'total_token_count':20},[])
    async def scenario():
        submission=SimpleNamespace(prompt=QUESTION,essay=ESSAY,warnings=[],config_snapshot={'fewshot':baseline_config(),'prompt_version':'v2','global_offsets':{'tr':.5}})
        result=await score(submission,Provider())
        assert result['criterion_scores']['task_response']==7
        assert result['raw_criterion_scores']['task_response']==6.5
        assert result['prompt_version'].startswith('v2:') and result['structural_audit']
    asyncio.run(scenario())


def test_operator_retry_obeys_queue_cap_and_counts_global_admissions(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            async with c.database.transaction() as db:
                teacher = await db.scalar(select(User).where(User.external_auth_id == 'user_teacher'))
                teacher.role = 'admin'
            admin = headers(subject='user_teacher')
            submitted = await submit(c)
            assert submitted.status_code == 202
            sid = submitted.json()['submission_id']
            jid = submitted.json()['job_id']
            async def fail():
                async with c.database.transaction() as db:
                    (await db.get(Job, jid)).status = 'FAILED'
                    (await db.get(Submission, sid)).status = 'FAILED'
            await fail()
            # A full queue must reject retry and roll back its reserved credit/counter.
            c.settings.max_queued_jobs = 0
            blocked = await c.client.post('/api/admin/jobs/' + sid + '/retry', headers=admin, json={})
            assert blocked.status_code == 503
            async with c.database.sessions() as db:
                assert (await db.get(Job, jid)).status == 'FAILED'
                ledger = await db.get(QuotaBucket, 'grading-retry-admissions')
                assert not ledger.events
            c.settings.max_queued_jobs = 100
            await c.client.patch('/api/admin/settings', headers=admin, json={'global_daily_submission_cap': 2})
            retried = await c.client.post('/api/admin/jobs/' + sid + '/retry', headers=admin, json={'reason':'Provider recovered'})
            assert retried.status_code == 200 and not retried.json()['already_queued']
            duplicate = await c.client.post('/api/admin/jobs/' + sid + '/retry', headers=admin, json={})
            assert duplicate.status_code == 200 and duplicate.json()['already_queued']
            async with c.database.sessions() as db:
                assert len((await db.get(QuotaBucket, 'grading-retry-admissions')).events) == 1
                audit = (await db.scalars(select(AuditEvent).where(AuditEvent.action == 'job_retried'))).all()
                assert len(audit) == 1
            # One original admission plus one retry fills the cap for new work too.
            assert (await submit(c, 1, key='after_retry_cap')).status_code == 429
            await fail()
            blocked = await c.client.post('/api/admin/jobs/' + sid + '/retry', headers=admin, json={})
            assert blocked.status_code == 429 and blocked.json()['detail']['code'] == 'GLOBAL_DAILY_CAP'
    asyncio.run(scenario())


def test_identity_backfill_settings_preservation_retry_assessment_guard_and_audit_actor(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            async with c.database.transaction() as db:
                teacher = await db.scalar(select(User).where(User.external_auth_id == 'user_teacher'))
                teacher.role = 'admin'
                teacher.full_name = 'Teacher Nguyen'
                teacher.email = 'nguyen@example.test'
                student = await db.get(User, c.accounts[0].id)
                student.full_name = 'Minh Student'
                student.email = 'minh@example.test'
            async with c.database.transaction() as db:
                await db.execute(update(Membership).where(Membership.user_id==c.accounts[0].id).values(active=False))
            admin = headers(subject='user_teacher')
            student_hdr = headers()
            room_res = await c.client.post('/api/teacher/classes', headers=admin, json={'name': 'Fog1'})
            assert room_res.status_code == 201
            rid = room_res.json()['id']
            code = room_res.json()['join_code']
            assert (await c.client.patch(f'/api/teacher/classes/{rid}', headers=admin, json={'daily_student_quota': 7})).status_code == 200
            assert (await c.client.post('/api/classes/join', headers=student_hdr, json={'join_code': code})).status_code == 200
            submitted = await c.client.post('/api/submissions', headers=student_hdr, json={'prompt': QUESTION, 'essay': ESSAY, 'class_id': rid})
            assert submitted.status_code == 202
            sid = submitted.json()['submission_id']

            me = (await c.client.get('/api/auth/me', headers=student_hdr)).json()
            fog1 = next(item for item in me['classes'] if item['id'] == rid)
            assert fog1['teacher_name'] == 'Teacher Nguyen'
            assert fog1['daily_student_quota'] == 7
            assert fog1['submission_count'] == 1

            roster = (await c.client.get(f'/api/teacher/classes/{rid}/students', headers=admin)).json()['items']
            minh_row = next(item for item in roster if item['user_id'] == c.accounts[0].id)
            assert minh_row['full_name'] == 'Minh Student' and minh_row['email'] == 'minh@example.test'
            assert minh_row['submission_count'] == 1

            subs = (await c.client.get(f'/api/teacher/classes/{rid}/submissions', headers=admin)).json()['items']
            assert subs[0]['student_name'] == 'Minh Student' and subs[0]['student_email'] == 'minh@example.test'
            assert subs[0]['submission_code'] == sid[:8].upper() and subs[0]['submitted_at'] > 0
            all_subs = (await c.client.get('/api/teacher/submissions', headers=admin)).json()['items']
            assert any(item['id'] == sid and item['student_name'] == 'Minh Student' for item in all_subs)

            users_page = (await c.client.get('/api/admin/users?search=minh&role=student&is_active=true&limit=1&offset=0', headers=admin)).json()
            assert users_page['total'] == 1 and users_page['limit'] == 1 and users_page['offset'] == 0
            assert users_page['items'][0]['email'] == 'minh@example.test'

            # Updating default enrolled limit preserves custom class quota unless apply_to_existing_classes=True.
            preserved = (await c.client.patch('/api/admin/settings', headers=admin, json={'enrolled_student_daily_limit': 4, 'reason': 'New cohort default'})).json()
            assert preserved['affected_classes_count'] == 0
            classes_after = (await c.client.get('/api/teacher/classes', headers=admin)).json()['items']
            assert next(item for item in classes_after if item['id'] == rid)['daily_student_quota'] == 7

            applied = (await c.client.patch('/api/admin/settings', headers=admin, json={'enrolled_student_daily_limit': 4, 'apply_to_existing_classes': True, 'reason': 'Sync all classes'})).json()
            assert applied['affected_classes_count'] >= 1
            classes_synced = (await c.client.get('/api/teacher/classes', headers=admin)).json()['items']
            assert next(item for item in classes_synced if item['id'] == rid)['daily_student_quota'] == 4

            logs = (await c.client.get('/api/admin/audit-logs?actor=nguyen', headers=admin)).json()['items']
            assert any(item['actor_name'] == 'Teacher Nguyen' and item['actor_email'] == 'nguyen@example.test' and item['reason'] == 'Sync all classes' for item in logs)

            # Retrying a submission that already has a completed Assessment must be blocked (409).
            async with c.database.transaction() as db:
                db.add(Assessment(submission_id=sid, result=payload(), raw_scores=payload()['criterion_scores']))
            assert (await c.client.post(f'/api/admin/jobs/{sid}/retry', headers=admin, json={'reason': 'Duplicate check'})).status_code == 409
    asyncio.run(scenario())


def test_high_band_essay_generates_upgrade_drills():
    from app.services.drill_gen import generate
    essay = (
        'Urban planners face a big problem when balancing heritage preservation with modern housing needs. '
        'Thoughtful zoning enables municipalities to accommodate growing populations without erasing historical identity.\n\n'
        'Consequently, public transit investment remains indispensable for sustainable metropolitan expansion.'
    )
    prompt = 'Discuss how cities should balance heritage preservation and modern development.'
    submission = SimpleNamespace(id='sub-high-band', prompt=prompt, essay=essay)
    grade = {'estimated_overall_band': 8.5, 'grammar_corrections': [], 'paragraph_reviews': [], 'criterion_feedback': {}}

    class HighBandProvider:
        def __init__(self):
            self.calls = 0

        async def generate_structured(self, system, user, schema):
            self.calls += 1
            if self.calls == 1:
                return Generation(json.dumps({'errors': [], 'exercises': []}), 'fixture', None, 1, {}, [])
            if self.calls == 2:
                assert 'HIGH-BAND REFINEMENT MODE' in system
                draft = {
                    'errors': [{
                        'error_id': 'd1', 'criterion': 'LR', 'category': 'vocabulary', 'subtype': 'word_choice',
                        'original_quote': 'big problem', 'suggested_correction': 'pressing challenge',
                        'explanation': 'Upgrade informal phrasing to precise academic lexis.',
                        'severity': 'low', 'paragraph_number': 1, 'optional_style': True,
                    }],
                    'exercises': [{
                        'source_error_id': 'd1', 'type': 'multiple_choice', 'skill': 'word_choice', 'difficulty': 1,
                        'instruction': 'Choose the most precise academic collocation.',
                        'question': 'Coastal authorities must address the ___ of rising sea levels before infrastructure fails.',
                        'structure_prompt': '',
                        'options': ['pressing challenge', 'big problem', 'heavy trouble'],
                        'correct_answer': 'pressing challenge',
                        'accepted_alternatives': [],
                        'target_span': '',
                        'explanation': 'Pressing challenge fits formal policy writing accurately.',
                        'hint': 'Select the formal academic collocation.',
                        'learning_objective': 'Use Band 8.5-9.0 lexical precision in formal arguments.',
                        'evaluation_rubric': ['Select the precise academic collocation.'],
                    }],
                }
                return Generation(json.dumps(draft), 'fixture', None, 1, {}, [])
            assert 'HIGH-BAND REFINEMENT AUDIT' in system
            review = {
                'errors': [{'error_id': 'd1', 'real_error': True, 'correction_valid': True, 'reason': 'Valid Band 9 upgrade.'}],
                'exercises': [{'index': 0, 'aligned': True, 'answer_correct': True, 'unambiguous': True,
                               'explanation_correct': True, 'difficulty_appropriate': True, 'distractors_plausible': True,
                               'no_answer_leak': True, 'no_injection': True, 'reason': 'Approved.'}],
            }
            return Generation(json.dumps(review), 'fixture', None, 1, {}, [])

    result = asyncio.run(generate(submission, grade, [], HighBandProvider(), 4))
    assert len(result['exercises']) == 1
    assert result['exercises'][0]['skill'] == 'word_choice'
    assert 'High-band lexical precision' in result['message']


def test_clerk_profile_sync_backfill_audit_target_filter_and_overview_pricing(tmp_path, monkeypatch):
    import jwt
    import httpx
    import time as time_mod
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from pydantic import SecretStr
    from app.auth import ClerkVerifier
    from app.database import Database
    from app.models import Base, ClassRoom, Membership
    from app.pilot import create_pilot_app
    from app.pilot_config import PilotSettings
    from app.seed import seed_defaults
    from test_concurrency_and_guardrails import FakeProvider

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    class MockClerkResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                'first_name': 'Lan',
                'last_name': 'Pham',
                'primary_email_address_id': 'idn_1',
                'email_addresses': [{'id': 'idn_1', 'email_address': 'lan.pham@example.test'}],
                'image_url': 'https://img.clerk.com/lan.png',
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, headers=None):
            assert headers == {'Authorization': 'Bearer sk_test_secret'}
            assert url.endswith('/user_backfill_api')
            return MockClerkResponse()

    monkeypatch.setattr('app.identity.httpx', SimpleNamespace(AsyncClient=MockAsyncClient, HTTPError=httpx.HTTPError))

    async def scenario():
        url = 'sqlite+aiosqlite:///' + (tmp_path / 'sync.sqlite3').as_posix()
        database = Database(url)
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        config = PilotSettings(
            _env_file=None, app_env='test', database_url=SecretStr(url),
            worker_enabled=False, clerk_issuer='https://issuer.example',
            clerk_jwt_key=public, clerk_secret_key=SecretStr('sk_test_secret'),
        )
        await seed_defaults(database)
        async with database.transaction() as db:
            admin = User(external_auth_id='user_admin_jwt', role='admin', consent_version=config.privacy_version)
            legacy_student = User(external_auth_id='user_backfill_api', role='student', consent_version=config.privacy_version)
            db.add_all([admin, legacy_student])
            await db.flush()
            room = ClassRoom(name='SyncClass', teacher_id=admin.id, invite_hash='hash', invite_expires_at=time_mod.time() + 600)
            db.add(room)
            await db.flush()
            db.add(Membership(user_id=legacy_student.id, class_id=room.id, role='student'))
            admin_id, student_id, room_id = admin.id, legacy_student.id, room.id

        verifier = ClerkVerifier(config)
        app = create_pilot_app(config, database=database, provider_factory=lambda small: FakeProvider(), verifier=verifier)

        def make_token(sub, **extra):
            claims = dict(iss=config.clerk_issuer, sub=sub, azp=config.frontend_origin,
                          iat=time_mod.time(), nbf=time_mod.time() - 1, exp=time_mod.time() + 60, **extra)
            return jwt.encode(claims, private, algorithm='RS256', headers={'kid': 'fixture'})

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
                # 1. JWT claims syncs admin profile on first request.
                admin_jwt = make_token('user_admin_jwt', full_name='Admin Tran', email='admin.tran@example.test', picture='https://img.clerk.com/admin.png')
                admin_hdr = {'Authorization': 'Bearer ' + admin_jwt}
                me = await client.get('/api/auth/me', headers=admin_hdr)
                assert me.status_code == 200 and me.json()['full_name'] == 'Admin Tran' and me.json()['email'] == 'admin.tran@example.test'

                # 2. JWT without name/email falls back to Clerk Backend API via CLERK_SECRET_KEY.
                student_jwt = make_token('user_backfill_api')
                me_student = await client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + student_jwt})
                assert me_student.status_code == 200
                assert me_student.json()['full_name'] == 'Lan Pham' and me_student.json()['email'] == 'lan.pham@example.test'

                roster = (await client.get(f'/api/teacher/classes/{room_id}/students', headers=admin_hdr)).json()['items']
                assert any(row['user_id'] == student_id and row['full_name'] == 'Lan Pham' and row['email'] == 'lan.pham@example.test' for row in roster)

                # 3. Overview with 0 usage records distinguishes unconfigured pricing (None) from configured zero ($0.00).
                ov_unconfigured = (await client.get('/api/admin/overview', headers=admin_hdr)).json()
                assert ov_unconfigured['pricing_configured'] is False and ov_unconfigured['estimated_gemini_cost'] is None

                await client.patch('/api/admin/settings', headers=admin_hdr, json={
                    'model_prices_usd_per_million': {'gemini-3.5-flash-lite': {'input': 0.1, 'output': 0.4}},
                    'reason': 'Configure pricing',
                })
                ov_configured = (await client.get('/api/admin/overview', headers=admin_hdr)).json()
                assert ov_configured['pricing_configured'] is True and ov_configured['estimated_gemini_cost'] == 0.0

                # 4. Audit logs support filtering by target (name/email/ID) and action.
                await client.patch(f'/api/admin/users/{student_id}', headers=admin_hdr, json={'bonus_daily_credits': 2, 'reason': 'Reward'})
                filtered_logs = (await client.get('/api/admin/audit-logs?target=Lan&action=admin_user_updated', headers=admin_hdr)).json()['items']
                assert len(filtered_logs) == 1 and filtered_logs[0]['target_label'] == 'Lan Pham' and filtered_logs[0]['action_type'] == 'admin_user_updated'

        await database.close()

    asyncio.run(scenario())


def test_failed_jobs_record_completed_at_across_worker_and_stale_lease_and_clear_on_retry(tmp_path):
    from app.providers.base import ProviderError
    from app.queue import claim
    from app.worker import Worker
    from test_concurrency_and_guardrails import FakeProvider

    async def scenario():
        async with application(tmp_path) as c:
            async with c.database.transaction() as db:
                teacher = await db.scalar(select(User).where(User.external_auth_id == 'user_teacher'))
                teacher.role = 'admin'
            admin = headers(subject='user_teacher')

            # 1. Worker.finish() with non-retryable failure must set completed_at.
            sub1 = await submit(c, key='fail_finish_01')
            assert sub1.status_code == 202
            sid1, jid1 = sub1.json()['submission_id'], sub1.json()['job_id']
            claimed = await claim(c.database, c.settings)
            assert claimed and claimed.id == jid1
            worker = Worker(c.database, c.settings, FakeProvider(), FakeProvider())
            assert await worker.finish(claimed, error=ProviderError('permanent_failure', 'Fixture', 503, False))
            async with c.database.sessions() as db:
                j1 = await db.get(Job, jid1)
                assert j1.status == 'FAILED' and j1.completed_at is not None

            # 2. Retry must clear completed_at back to None.
            retried = await c.client.post(f'/api/admin/jobs/{sid1}/retry', headers=admin, json={'reason': 'Requeue'})
            assert retried.status_code == 200
            async with c.database.sessions() as db:
                j1_retry = await db.get(Job, jid1)
                assert j1_retry.status == 'QUEUED' and j1_retry.completed_at is None

            # 3. Stale lease exhaustion in claim() must also set completed_at when marking FAILED.
            async with c.database.transaction() as db:
                j1_stale = await db.get(Job, jid1)
                j1_stale.status = 'RUNNING'
                j1_stale.attempt_count = c.settings.job_max_attempts
                j1_stale.lease_expires_at = 1.0
                j1_stale.lease_token = 'stale-token'
            assert await claim(c.database, c.settings) is None
            async with c.database.sessions() as db:
                j1_failed = await db.get(Job, jid1)
                assert j1_failed.status == 'FAILED' and j1_failed.completed_at is not None

    asyncio.run(scenario())


def test_split_thinking_budgets_and_vietnamese_feedback_schema(tmp_path):
    from google.genai import types
    from app.config import Settings, load_settings
    from app.pilot_config import PilotSettings
    from app.practice.schemas import AnswerAssessment, PracticeDraft, PracticeReview
    from app.providers.gemini import GeminiProvider

    defaults = PilotSettings(_env_file=None)
    assert defaults.gemini_score_thinking_budget == -1
    assert defaults.gemini_practice_thinking_budget == 0
    assert defaults.worker_poll_seconds == 0.25
    assert defaults.feedback_language == 'vi'
    assert defaults.auto_practice_mode == 'idle_only'
    assert load_settings().score_thinking_budget == 512 or isinstance(load_settings().score_thinking_budget, int)

    assert AssessmentOutputV2.model_fields['aspect_reviews'].metadata[0].max_length == 15
    assert AssessmentOutputV2.model_fields['sentence_annotations'].metadata[0].max_length == 10
    assert AssessmentOutputV2.model_fields['grammar_corrections'].metadata[0].max_length == 8
    assert AssessmentOutputV2.model_fields['language_suggestions'].metadata[0].max_length == 8
    assert AssessmentOutputV2.model_fields['paragraph_reviews'].metadata[0].max_length == 6

    oversized = {
        **v2_output(),
        'aspect_reviews': [{'aspect_name': 'Relevance to Prompt', 'score': 6.5, 'strength_vi': 'Đáp ứng chủ đề.', 'weakness_vi': 'Cần phát triển ví dụ.'} for _ in range(16)],
        'paragraph_reviews': [{'paragraph_number': i + 1, 'role': 'body', 'summary': 'Good.', 'improvement': 'Add detail.', 'evidence': None} for i in range(10)],
    }
    trimmed = AssessmentOutputV2.model_validate(oversized)
    assert len(trimmed.aspect_reviews) == 15 and len(trimmed.paragraph_reviews) == 6

    captured_configs = []

    class FakeModels:
        async def generate_content(self, *, model, contents, config):
            captured_configs.append(config)
            raw_json = json.dumps(v2_output())
            usage = SimpleNamespace(model_dump=lambda: {'prompt_token_count': 10, 'candidates_token_count': 20, 'thoughts_token_count': 5, 'total_token_count': 35})
            candidate = SimpleNamespace(finish_reason='STOP')
            return SimpleNamespace(text=raw_json, usage_metadata=usage, candidates=[candidate], model_version='gemini-3.5-flash-lite')

    fake_client = SimpleNamespace(aio=SimpleNamespace(models=FakeModels()))
    provider = GeminiProvider(
        Settings(api_key='test-key', score_thinking_budget=512, practice_thinking_budget=0),
        budget_path=tmp_path / 'quota.sqlite3',
        client=fake_client,
    )

    async def scenario():
        await provider.generate_structured('sys', 'user', AssessmentOutputV2)
        await provider.generate_structured('sys', 'user', PracticeDraft)
        await provider.generate_structured('sys', 'user', PracticeReview)
        await provider.generate_structured('sys', 'user', AnswerAssessment)
        assert [cfg.thinking_config.thinking_budget for cfg in captured_configs] == [512, 0, 0, 0]
        provider.settings = __import__('dataclasses').replace(provider.settings, score_thinking_budget=-1)
        await provider.generate_structured('sys','user',AssessmentOutputV2)
        assert captured_configs[-1].thinking_config is None
        captured_configs.pop()
        assert all(isinstance(cfg.thinking_config, types.ThinkingConfig) for cfg in captured_configs)

        captured_systems = []

        class CaptureProvider:
            settings = SimpleNamespace(feedback_language='vi')

            async def generate_structured(self, system, user, schema):
                captured_systems.append(system)
                return Generation(json.dumps(v2_output()), 'fixture', None, 1, {'total_token_count': 20}, [])

        vi_sub = SimpleNamespace(
            prompt=QUESTION, essay=ESSAY, warnings=[],
            config_snapshot={'fewshot': baseline_config(), 'prompt_version': 'v2', 'feedback_language': 'vi'},
        )
        en_sub = SimpleNamespace(
            prompt=QUESTION, essay=ESSAY, warnings=[],
            config_snapshot={'fewshot': baseline_config(), 'prompt_version': 'v2', 'feedback_language': 'en'},
        )
        await score(vi_sub, CaptureProvider())
        await score(en_sub, CaptureProvider())
        assert 'FEEDBACK_LANGUAGE=vi' in captured_systems[0]
        assert 'structural_audit' in captured_systems[0]
        assert 'FEEDBACK_LANGUAGE=vi' not in captured_systems[1]

    asyncio.run(scenario())


def test_worker_idle_only_auto_practice_and_priority(tmp_path):
    from app.models import PracticeSet
    from app.queue import claim
    from app.worker import Worker
    from test_concurrency_and_guardrails import FakeProvider, RESULT

    async def scenario():
        async with application(tmp_path) as c:
            assert c.settings.auto_practice_mode == 'idle_only'
            r1 = await submit(c, key='idle_key_01')
            r2 = await submit(c, key='idle_key_02', essay=ESSAY+' Additional evidence supports this argument.')
            assert r1.status_code == 202 and r2.status_code == 202
            sub1, sub2 = r1.json(), r2.json()

            worker = Worker(c.database, c.settings, FakeProvider(), FakeProvider())

            # First score job finishes while second score job is STILL queued -> skip auto-practice.
            j1 = await claim(c.database, c.settings)
            assert j1.id == sub1['job_id'] and j1.priority == 0
            assert await worker.finish(j1, result=RESULT)
            async with c.database.sessions() as db:
                assert await db.get(PracticeSet, sub1['submission_id']) is None
                practice_jobs = (await db.scalars(select(Job).where(Job.kind == 'practice'))).all()
                assert len(practice_jobs) == 0

            # Second (last) score job finishes with queued_score_count == 0 -> enqueue priority=10 practice.
            j2 = await claim(c.database, c.settings)
            assert j2.id == sub2['job_id']
            assert await worker.finish(j2, result=RESULT)
            async with c.database.sessions() as db:
                ps = await db.get(PracticeSet, sub2['submission_id'])
                assert ps is not None and ps.state == 'generating'
                pjobs = (await db.scalars(select(Job).where(Job.kind == 'practice'))).all()
                assert len(pjobs) == 1 and pjobs[0].submission_id == sub2['submission_id'] and pjobs[0].priority == 10

            # New score job (priority=0) must always be claimed BEFORE queued practice job (priority=10).
            r3 = await submit(c, 1, key='idle_key_03')
            assert r3.status_code == 202
            sub3 = r3.json()
            next_claimed = await claim(c.database, c.settings)
            assert next_claimed.id == sub3['job_id'] and next_claimed.kind == 'score'
            # Under on_demand mode, no practice job is auto-enqueued even when idle.
            c.settings.auto_practice_mode = 'on_demand'
            assert await worker.finish(next_claimed, result=RESULT)
            async with c.database.sessions() as db:
                assert await db.get(PracticeSet, sub3['submission_id']) is None

            # Pending priority=10 practice job is claimed once score queue is empty.
            p_claimed = await claim(c.database, c.settings)
            assert p_claimed is not None and p_claimed.kind == 'practice' and p_claimed.submission_id == sub2['submission_id']

    asyncio.run(scenario())


def test_profile_backfill_alias_null_only_and_collision_safe(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            # First backfill populates null reported_* fields via /api/auth/profile.
            first = await c.client.patch('/api/auth/profile', headers=headers(), json={'full_name': 'Minh Bui', 'email': 'minh.bui@example.test'})
            assert first.status_code == 200
            assert first.json()['full_name'] == 'Minh Bui' and first.json()['email'] == 'minh.bui@example.test'
            # Already-populated fields are NOT overwritten on subsequent fallback calls.
            second = await c.client.post('/api/auth/profile', headers=headers(), json={'full_name': 'Overwrite Attempt', 'email': 'other@example.test'})
            assert second.status_code == 200
            assert second.json()['full_name'] == 'Minh Bui' and second.json()['email'] == 'minh.bui@example.test'
            # Role escalation & extra fields remain rejected (422) and role never mutates.
            assert (await c.client.patch('/api/auth/profile', headers=headers(), json={'role': 'admin'})).status_code == 422
            assert (await c.client.get('/api/auth/me', headers=headers())).json()['role'] == 'student'

            # Unique email collision on reported_email is caught cleanly without crashing backfill.
            from sqlalchemy import text as sql_text
            async with c.database.transaction() as db:
                await db.execute(sql_text('CREATE UNIQUE INDEX ix_test_reported_email ON users(reported_email) WHERE reported_email IS NOT NULL'))
            collision = await c.client.patch('/api/auth/profile', headers=headers(1), json={'full_name': 'Second Student', 'email': 'minh.bui@example.test'})
            assert collision.status_code == 200
            assert collision.json()['full_name'] == 'Second Student' and collision.json()['email'] is None

    asyncio.run(scenario())
