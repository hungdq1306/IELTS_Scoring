"""Run with TEST_DATABASE_URL pointing ONLY at an isolated fogwrite_test database.

Gemini is mocked; PostgreSQL locks, transactions and HTTP authorization are real.
Without TEST_DATABASE_URL the deterministic unit adapter is SQLite (not a load claim).
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select, update

from app.auth import ClerkVerifier
from app.database import Database
from app.grading.schemas import Scores
from app.grading.task2 import overall_band
from app.guardrails import redact_pii, validate_input
from app.models import Assessment, Base, ClassRoom, Job, Membership, PracticeSet, Submission, User
from app.pilot import create_pilot_app
from app.pilot_config import PilotSettings
from app.providers.base import ProviderError
from app.queue import claim
from app.seed import seed_defaults
from app.services.budget import DatabaseBudget
from app.services.drill_gen import generate, public_practice
from app.worker import Worker

ESSAY = ('Cities need reliable public transport because many residents depend on buses to reach work. '
         'Frequent services reduce waiting times and make journeys more predictable. Governments should '
         'also maintain safe walking routes around stations. This approach gives people a practical '
         'alternative to driving and can reduce congestion in busy neighbourhoods. Clear information '
         'about routes helps new passengers travel confidently while affordable tickets support families.')
QUESTION = 'How should a city improve everyday transport for its residents?'
RESULT = {'criterion_scores': {key: 6.5 for key in ('task_response', 'coherence_cohesion', 'lexical_resource', 'grammatical_range_accuracy')},
          'estimated_overall_band': 6.5, 'validation_warnings': []}


class FakeVerifier:
    async def verify(self, token):
        if not token.startswith('user_'):
            raise HTTPException(401, 'Invalid token')
        return token


class FakeProvider:
    settings = SimpleNamespace(model='offline-small-model')
    async def close(self): pass


@asynccontextmanager
async def application(tmp_path, students=2):
    url = os.getenv('TEST_DATABASE_URL', 'sqlite+aiosqlite:///' + (tmp_path / 'pilot.sqlite3').as_posix())
    if not url.startswith('sqlite') and not url.split('?')[0].endswith('/fogwrite_test'):
        raise RuntimeError('Refusing to reset a database not named fogwrite_test.')
    database = Database(url)
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    config = PilotSettings(_env_file=None, app_env='test', database_url=SecretStr(url),
                           worker_enabled=False, worker_poll_seconds=.05, worker_lease_seconds=10,
                           clerk_issuer='https://example.clerk.accounts.dev')
    await seed_defaults(database)
    async with database.transaction() as session:
        teacher = User(external_auth_id='user_teacher', role='teacher', consent_version=config.privacy_version)
        other = User(external_auth_id='user_other_teacher', role='teacher', consent_version=config.privacy_version)
        session.add_all([teacher, other]); await session.flush()
        room = ClassRoom(name='Pilot', teacher_id=teacher.id, invite_hash='unused-hash', invite_expires_at=time.time()+600)
        other_room = ClassRoom(name='Other', teacher_id=other.id, invite_hash='other-hash', invite_expires_at=time.time()+600)
        session.add_all([room, other_room]); await session.flush()
        accounts = []
        for index in range(students):
            user = User(external_auth_id='user_student' + str(index), consent_version=config.privacy_version)
            session.add(user); await session.flush()
            session.add(Membership(user_id=user.id, class_id=room.id))
            accounts.append(user)
        session.add(Membership(user_id=teacher.id, class_id=room.id, role='teacher'))
        ta = User(external_auth_id='user_ta', role='ta', consent_version=config.privacy_version)
        session.add(ta); await session.flush()
        session.add(Membership(user_id=ta.id, class_id=room.id, role='ta'))
    app = create_pilot_app(config, database=database, provider_factory=lambda small: FakeProvider(), verifier=FakeVerifier())
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
                yield SimpleNamespace(app=app, client=client, database=database, settings=config,
                                      accounts=accounts, room=room, other_room=other_room)
    finally:
        await database.close()


def headers(index=0, key='request_0001', subject=None):
    return {'Authorization': 'Bearer ' + (subject or 'user_student' + str(index)), 'Idempotency-Key': key}


async def submit(context, index=0, key='request_0001', essay=ESSAY):
    return await context.client.post('/api/submissions', headers=headers(index, key), json={'prompt': QUESTION, 'essay': essay})


def test_40_submissions_no_duplicate_claims_or_pool_errors(tmp_path):
    async def scenario():
        async with application(tmp_path, 40) as context:
            responses = await asyncio.gather(*(submit(context, index) for index in range(40)))
            assert all(response.status_code == 202 for response in responses), [response.text for response in responses if response.status_code != 202]
            ids = {response.json()['submission_id'] for response in responses}
            assert len(ids) == 40
            seen = set()
            async def score(job):
                assert job.submission_id not in seen
                seen.add(job.submission_id)
                await asyncio.sleep(.005)
                return RESULT
            async def drain():
                worker = Worker(context.database, context.settings, FakeProvider(), FakeProvider(), handler=score)
                while job := await claim(context.database, context.settings):
                    await worker.process(job)
            await asyncio.gather(*(drain() for _ in range(4)))
            async with context.database.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(Assessment)) == 40
                assert await session.scalar(select(func.count()).select_from(Job).where(Job.status == 'COMPLETED')) == 40
            assert seen == ids
            status = await context.client.get(responses[0].json()['poll_url'], headers=headers())
            assert status.json()['result']['estimated_overall_band'] == 6.5
    asyncio.run(scenario())


def test_concurrent_quota_and_idempotency(tmp_path):
    async def scenario():
        async with application(tmp_path) as context:
            duplicates = await asyncio.gather(*(submit(context, key='same_request') for _ in range(12)))
            assert {response.status_code for response in duplicates} == {202}
            assert len({response.json()['job_id'] for response in duplicates}) == 1
            conflict = await submit(context, key='same_request', essay=ESSAY + ' Additional evidence improves this argument.')
            assert conflict.status_code == 409
            responses = await asyncio.gather(*(submit(context, key='quota_key_' + str(index)) for index in range(9)))
            assert sum(response.status_code == 202 for response in responses) == 2
            assert sum(response.status_code == 429 for response in responses) == 7
            assert all('retry-after' in response.headers for response in responses if response.status_code == 429)
    asyncio.run(scenario())


def test_owner_role_class_and_revocation_guards(tmp_path):
    async def scenario():
        async with application(tmp_path) as context:
            response = (await submit(context)).json()
            assert (await context.client.get(response['poll_url'], headers=headers(1))).status_code == 404
            sid = response['submission_id']
            assert (await context.client.get('/api/submissions/' + sid, headers=headers(1))).status_code == 404
            assert (await context.client.get('/api/teacher/classes', headers=headers())).status_code == 403
            assert (await context.client.get('/api/teacher/classes/' + context.room.id + '/submissions', headers=headers(subject='user_ta'))).status_code == 200
            assert (await context.client.get('/api/teacher/classes/' + context.other_room.id + '/submissions', headers=headers(subject='user_ta'))).status_code == 404
            assert (await context.client.post('/api/teacher/classes', headers=headers(subject='user_ta'), json={'name':'Escalation'})).status_code == 403
            async with context.database.transaction() as session:
                await session.execute(update(Membership).where(Membership.user_id == context.accounts[0].id).values(active=False))
            assert (await context.client.get('/api/submissions/' + sid, headers=headers())).status_code == 403
            assert (await submit(context, key='after_revoke')).status_code == 403
            assert (await context.client.get('/api/benchmarks')).status_code == 404
            assert (await context.client.get('/api/fewshot/lecturer/examples')).status_code == 404
    asyncio.run(scenario())


def test_stale_lease_fences_old_worker_and_claim_order(tmp_path):
    async def scenario():
        async with application(tmp_path) as context:
            responses = [await submit(context, key='ordered_key_' + str(index)) for index in range(3)]
            first = await claim(context.database, context.settings)
            assert first.id == responses[0].json()['job_id']
            async with context.database.transaction() as session:
                await session.execute(update(Job).where(Job.id == first.id).values(lease_expires_at=time.time()-1))
            reclaimed = await claim(context.database, context.settings)
            assert reclaimed.id == first.id and reclaimed.lease_token != first.lease_token and reclaimed.attempt_count == 2
            worker = Worker(context.database, context.settings, FakeProvider(), FakeProvider())
            assert not await worker.finish(first, result=RESULT)
            assert await worker.finish(reclaimed, result=RESULT)
            second = await claim(context.database, context.settings)
            assert second.id == responses[1].json()['job_id']
            await worker.finish(second, error=ProviderError('upstream_unavailable','fixture',503,True))
            async with context.database.sessions() as session:
                assert (await session.get(Job, second.id)).status == 'QUEUED'
                assert await session.scalar(select(func.count()).select_from(Assessment)) == 1
    asyncio.run(scenario())


def test_join_invite_and_bruteforce_budget(tmp_path):
    async def scenario():
        async with application(tmp_path) as context:
            async with context.database.transaction() as db:
                await db.execute(update(Membership).where(Membership.user_id.in_([u.id for u in context.accounts])).values(active=False))
            teacher = headers(subject='user_teacher')
            response = await context.client.post('/api/teacher/classes', headers=teacher, json={'name':'YP03','invite_max_uses':1})
            assert response.status_code == 201
            code = response.json()['join_code']
            assert len(code) == 8 and code != 'YP03'
            body = {'join_code':code,'adult_confirmed':True,'accepted_privacy':True}
            assert (await context.client.post('/api/classes/join', headers=headers(),json=body)).status_code == 200
            assert (await context.client.post('/api/classes/join', headers=headers(1),json=body)).status_code == 400
            for _ in range(9):
                assert (await context.client.post('/api/classes/join', headers=headers(1),json={**body,'join_code':'wrong-invite-code-long-enough'})).status_code == 400
            assert (await context.client.post('/api/classes/join', headers=headers(1),json=body)).status_code == 429
    asyncio.run(scenario())


def test_input_schema_rounding_and_pii():
    count, warnings = validate_input(QUESTION, ESSAY)
    assert 50 <= count < 250 and 'under_250_words' in warnings
    for essay in ['tiny response', 'word ' * 100, ESSAY * 30]:
        with pytest.raises(HTTPException): validate_input(QUESTION, essay)
    with pytest.raises(ValidationError): Scores(task_response=99, coherence_cohesion=6, lexical_resource=6, grammatical_range_accuracy=6)
    with pytest.raises(ValidationError): Scores(task_response=6.1, coherence_cohesion=6, lexical_resource=6, grammatical_range_accuracy=6)
    assert overall_band(Scores(task_response=6,coherence_cohesion=6,lexical_resource=6,grammatical_range_accuracy=7)) == 6.5
    assert overall_band(Scores(task_response=6,coherence_cohesion=7,lexical_resource=7,grammatical_range_accuracy=7)) == 7.0
    text = 'Contact student@example.com or +84 987 654 321.'
    clean = redact_pii(text)
    assert 'student@example.com' not in clean and '987' not in clean and len(clean) == len(text)


def test_real_jwt_verification_and_fail_closed():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    settings = PilotSettings(_env_file=None,app_env='test',clerk_issuer='https://issuer.example',clerk_jwt_key=public)
    verifier = ClerkVerifier(settings)
    def token(**overrides):
        claims = dict(iss=settings.clerk_issuer,sub='user_valid',azp=settings.frontend_origin,iat=time.time(),nbf=time.time()-1,exp=time.time()+60)
        return jwt.encode(claims|overrides, private, algorithm='RS256',headers={'kid':'fixture'})
    async def scenario():
        assert await verifier.verify(token()) == 'user_valid'
        for bad in [token(azp='https://evil.example'),token(iss='https://evil.example'),token(exp=time.time()-60),token(nbf=time.time()+60),'not-a-jwt']:
            with pytest.raises(HTTPException) as error: await verifier.verify(bad)
            assert error.value.status_code == 401
    asyncio.run(scenario())


def test_shared_gemini_daily_budget_is_atomic(tmp_path):
    async def scenario():
        async with application(tmp_path) as context:
            config = context.settings.model_copy(update={'gemini_max_rpd':3,'gemini_max_rpm':100})
            budgets = [DatabaseBudget(context.database,config) for _ in range(4)]
            results = await asyncio.gather(*(budget.acquire() for budget in budgets),return_exceptions=True)
            assert sum(result is None for result in results) == 3
            assert sum(isinstance(result,ProviderError) and result.code=='daily_quota' for result in results) == 1
    asyncio.run(scenario())


def test_provisional_practice_schema_and_no_answer_leak():
    from test_practice import FakeProvider as PracticeProvider
    from app.practice.schemas import PracticeResponse
    async def scenario():
        submission = SimpleNamespace(id='fixture-submission',prompt=QUESTION,essay='Technology help students access useful materials. It give learners more flexibility.')
        draft = await generate(submission,{},[],PracticeProvider(),4)
        response = public_practice(submission.id,'ready',draft)
        PracticeResponse.model_validate(response)
        assert response['exercises']
        assert all('correct_answer' not in item and 'accepted_alternatives' not in item for item in response['exercises'])
        assert all(error['original_quote'] in submission.essay for error in response['errors'])
    asyncio.run(scenario())


def test_request_limits_and_missing_auth(tmp_path):
    async def scenario():
        async with application(tmp_path) as context:
            assert (await context.client.get('/api/auth/me')).status_code == 401
            assert (await context.client.post('/api/submissions',content='x'*70000,headers=headers())).status_code == 413
            response = await context.client.post('/api/submissions',headers=headers(),json={'prompt':QUESTION,'essay':ESSAY,'role':'admin'})
            assert response.status_code == 422 and 'input' not in response.json()['detail'][0]
            assert (await context.client.options('/api/submissions',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'POST'})).status_code == 400
            assert (await context.client.get('/ready')).status_code == 200
    asyncio.run(scenario())


def test_scoring_practice_batch_and_teacher_override_e2e(tmp_path):
    from test_practice import FakeProvider as PracticeProvider
    from app.practice.schemas import BatchAssessment
    from app.providers.base import Generation
    class Provider(PracticeProvider):
        settings = SimpleNamespace(model='offline-small-model')
        async def generate_structured(self, system, user, schema):
            from app.grading.v2 import AssessmentOutputV2
            if schema is AssessmentOutputV2:
                from test_rbac_and_ai_v2 import v2_output
                return Generation(json.dumps(v2_output()),self.settings.model,None,1,{},[])
            if schema is BatchAssessment:
                data = json.loads(user)
                items = [{'exercise_id': row['exercise']['exercise_id'], 'outcome':'correct',
                          'explanation':'The response fixes the target while preserving the meaning.',
                          'suggested_improvement':'', 'target_fixed':True, 'meaning_preserved':True,
                          'no_new_serious_errors':True} for row in data['responses']]
                return Generation(json.dumps({'items':items,'summary':'Practise this agreement pattern in new contexts.'}),
                                  self.settings.model,None,1,{},[])
            return await super().generate_structured(system,user,schema)
    async def scenario():
        async with application(tmp_path) as context:
            provider = Provider()
            worker = Worker(context.database,context.settings,provider,provider)
            response = await submit(context,essay='Technology help students access useful materials. It give learners more flexibility. '+ESSAY)
            assert response.status_code == 202
            sid = response.json()['submission_id']
            await worker.process(await claim(context.database,context.settings))
            graded = await context.client.get('/api/submissions/'+sid,headers=headers())
            assert graded.json()['status'] == 'COMPLETED', (await context.client.get(response.json()['poll_url'],headers=headers())).json()
            assert graded.json()['grade']['confidence'] is None
            queued = await context.client.post('/api/writing/task2/'+sid+'/exercises',headers=headers())
            assert queued.status_code == 202
            await worker.process(await claim(context.database,context.settings))
            public = (await context.client.get('/api/writing/task2/'+sid+'/exercises',headers=headers())).json()
            assert public['state'] == 'ready' and public['exercises'], public
            assert all('correct_answer' not in row for row in public['exercises'])
            answers = [{'exercise_id': row['exercise_id'],'answer':'helps' if row['type']=='multiple_choice' else 'A valid alternative correction.'} for row in public['exercises']]
            path = '/api/writing/task2/'+sid+'/practice-attempt'
            assert (await context.client.put(path,headers=headers(),json={'answers':answers})).status_code == 200
            batch = await context.client.post(path+'/submit',headers=headers(),json={'answers':answers,'request_id':'batch_request_01'})
            repeated = await context.client.post(path+'/submit',headers=headers(),json={'answers':answers,'request_id':'batch_request_01'})
            assert batch.status_code == 202 and batch.json()['job_id'] == repeated.json()['job_id']
            await worker.process(await claim(context.database,context.settings))
            result = (await context.client.get(batch.json()['poll_url'],headers=headers())).json()
            assert result['status'] == 'COMPLETED', result
            assert result['result']['total'] == len(answers)
            assert result['result']['correct_count'] == len(answers)
            assert (await context.client.get(path,headers=headers())).json()['state'] == 'complete'
            override = {'scores':{key:7.0 for key in RESULT['criterion_scores']},'reason':'Reviewed independently by the teacher.'}
            assert (await context.client.put('/api/teacher/submissions/'+sid+'/override',headers=headers(subject='user_ta'),json=override)).status_code == 404
            assert (await context.client.put('/api/teacher/submissions/'+sid+'/override',headers=headers(subject='user_teacher'),json=override)).status_code == 200
            saved = (await context.client.get('/api/submissions/'+sid,headers=headers())).json()
            assert saved['grade']['teacher_reviewed'] and saved['grade']['estimated_overall_band'] == 7.0
            async with context.database.sessions() as session:
                assert (await session.get(Assessment,sid)).raw_scores != override['scores']
    asyncio.run(scenario())


def test_assignment_anchor_exclusion_preserves_copy_protection():
    from app.services.scorer import assignment_safe_config, baseline_config
    from app.grading.fewshot import protect
    from app.grading.schemas import GradeRequest
    config = baseline_config()
    example = config['examples'][0]
    adjusted = assignment_safe_config(config, example['question'])
    assert len(adjusted['examples']) < 8 and len(config['examples']) == 8
    protect(GradeRequest(prompt=example['question'],essay=ESSAY),adjusted)
    with pytest.raises(ProviderError):
        protect(GradeRequest(prompt=example['question'],essay=example['student_essay']),adjusted)
