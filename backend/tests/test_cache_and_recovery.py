"""HTTP/database regressions; providers are offline fixtures, never Gemini calls."""
import asyncio
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models import Assessment, ClassRoom, Job, Membership, PracticeExercise, PracticeSet, Submission, SystemSetting, TeacherProfile
from app.practice.schemas import ExerciseDraft
from app.providers.base import ProviderError
from app.queue import claim
from app.services.submission_cache import answers_hash, content_hash
from app.worker import Worker
from test_concurrency_and_guardrails import application, headers, submit, ESSAY, RESULT


def exercise(index=0):
    item = ExerciseDraft(source_error_id='e', type='multiple_choice', skill='word_choice', difficulty=1,
        instruction='Choose a word.', question='Choose the best answer.', options=['a', 'b', 'c'],
        correct_answer='a', accepted_alternatives=[], target_span='', explanation='A is correct.', hint='Choose a.',
        learning_objective='Choose appropriate words.', evaluation_rubric=['Correct choice'])
    return {**item.model_dump(), 'exercise_id': f'ex-{index}', 'validation_status': 'machine_reviewed_not_human_verified'}


async def ready_practice(c, count=1, indexed=True):
    async with c.database.transaction() as db:
        for i in range(count):
            s = Submission(id=f'review-{i}', user_id=c.accounts[0].id, class_id=c.room.id,
                           prompt='Original question', essay=ESSAY, word_count=65, status='COMPLETED', config_snapshot={})
            db.add(s); await db.flush()
            db.add(Assessment(submission_id=s.id, result=RESULT, raw_scores={}))
            db.add(PracticeSet(submission_id=s.id, state='ready', payload={'errors': [], 'exercises': [exercise(i)]}))
        await db.flush()
        if indexed:
            db.add_all([PracticeExercise(exercise_id=f'ex-{i}', submission_id=f'review-{i}') for i in range(count)])


def test_exact_cache_at_zero_credits_and_concurrent_inflight(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            c.settings.auto_practice_mode = 'on_demand'
            async with c.database.transaction() as db:
                (await db.get(ClassRoom, c.room.id)).daily_student_quota = 1
            requests = await asyncio.gather(*(submit(c, key=f'parallel_{i}') for i in range(8)))
            assert {r.status_code for r in requests} == {202}
            assert len({r.json()['job_id'] for r in requests}) == 1
            conflict = await submit(c, key='parallel_1', essay=ESSAY+' Changed content.')
            assert conflict.status_code == 409  # Reconnected aliases retain idempotency too.
            calls = []
            async def offline_score(job):
                calls.append(job.id)
                return RESULT
            worker = Worker(c.database, c.settings, None, None, handler=offline_score)
            await worker.process(await claim(c.database, c.settings))
            # A cache hit is available even with no credits; no new work or credit is reserved.
            cached = await submit(c, key='cache_at_zero')
            assert cached.status_code == 200 and cached.json()['reused'] is True
            assert cached.json()['submission_id'] == requests[0].json()['submission_id']
            assert (await submit(c, key='cache_at_zero')).json()['reused'] is True
            assert (await submit(c, key='cache_at_zero', essay=ESSAY+' Changed content.')).status_code == 409
            assert await claim(c.database, c.settings) is None and len(calls) == 1
            me = (await c.client.get('/api/auth/me', headers=headers())).json()
            assert me['quota_status']['used_today'] == 1 and me['quota_status']['remaining_today'] == 0
            async with c.database.sessions() as db:
                assert await db.scalar(select(func.count()).select_from(Submission)) == 1
                assert await db.scalar(select(func.count()).select_from(Job)) == 1
            async with c.database.transaction() as db:
                membership = await db.scalar(select(Membership).where(Membership.user_id == c.accounts[0].id))
                membership.active, membership.removed_at = False, time.time()
            assert (await submit(c, key='cache_after_removal')).status_code == 403
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['word', 'user', 'prompt_version', 'calibration', 'teacher', 'model', 'thinking', 'failed'])
def test_cache_misses_for_different_content_or_grading_context(tmp_path, change):
    async def scenario():
        async with application(tmp_path) as c:
            c.settings.auto_practice_mode = 'on_demand'
            first = await submit(c)
            job = await claim(c.database, c.settings)
            worker = Worker(c.database, c.settings, None, None)
            if change == 'failed':
                await worker.finish(job, error=ProviderError('fixture_failure', 'offline', 503, False))
            else:
                await worker.finish(job, result=RESULT)
            async with c.database.transaction() as db:
                setting = await db.get(SystemSetting, 'pilot')
                if change in ('prompt_version', 'calibration'):
                    if setting is None:
                        setting = SystemSetting(key='pilot', value={})
                        db.add(setting)
                    setting.value = {**setting.value, **({'active_prompt_version': 'v1'} if change == 'prompt_version' else {'calibration_offsets_json': {'tr': .5}})}
                if change == 'teacher':
                    profile = await db.get(TeacherProfile, c.room.teacher_id)
                    if profile: profile.style = 'Give concise explanations.'
                    else: db.add(TeacherProfile(teacher_id=c.room.teacher_id, style='Give concise explanations.'))
            if change == 'model': c.app.state.provider.settings = SimpleNamespace(model='another-offline-model')
            if change == 'thinking': c.app.state.provider.settings = SimpleNamespace(model=c.app.state.provider.settings.model, score_thinking_budget=1024)
            second = await submit(c, 1 if change == 'user' else 0, key='cache_miss_request',
                                  essay=ESSAY.replace('Cities', 'Towns', 1) if change == 'word' else ESSAY)
            assert second.status_code == 202, second.text
            assert second.json()['submission_id'] != first.json()['submission_id']
    asyncio.run(scenario())


def test_hash_preserves_paragraphs_and_scopes_class_and_language():
    base = content_hash('u', 'c', 'Question', 'one\r\n\r\ntwo', {'feedback_language': 'vi'}, 'm')
    assert base == content_hash('u', 'c', 'Question', 'one\n\ntwo', {'feedback_language': 'vi'}, 'm')
    assert base != content_hash('u', 'c', 'Question', 'one two', {'feedback_language': 'vi'}, 'm')
    assert base != content_hash('u', 'other', 'Question', 'one\n\ntwo', {'feedback_language': 'vi'}, 'm')
    assert base != content_hash('u', 'c', 'Question', 'one\n\ntwo', {'feedback_language': 'en'}, 'm')


def test_failed_details_and_fresh_resubmission(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            response = await submit(c)
            worker = Worker(c.database, c.settings, None, None)
            await worker.finish(await claim(c.database, c.settings), error=ProviderError('provider_timeout', 'offline', 503, False))
            saved = (await c.client.get('/api/writing/task2/'+response.json()['submission_id']+'/submission', headers=headers())).json()
            assert saved['essay'] == ESSAY and saved['prompt'] and saved['word_count'] >= 50
            assert saved['status'] == 'FAILED' and saved['grade'] is None and saved['credit_refunded']
            assert saved['error_code'] == 'provider_timeout' and saved['error_message']
            assert (await submit(c, key='resubmit_failed')).status_code == 202
    asyncio.run(scenario())


def test_saved_answers_invalidate_feedback_and_late_job_cannot_restore_it(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            await ready_practice(c)
            path = '/api/writing/task2/review-0/practice-attempt'
            first = {'answers': [{'exercise_id': 'ex-0', 'answer': 'a'}]}
            posted = await c.client.post(path+'/submit', headers=headers(), json={**first, 'request_id': 'practice_first'})
            job = await claim(c.database, c.settings)
            assert posted.status_code == 202
            edited = {'answers': [{'exercise_id': 'ex-0', 'answer': 'b'}]}
            assert (await c.client.put(path, headers=headers(), json=edited)).status_code == 200
            assert await Worker(c.database, c.settings, None, None).finish(job, result={'items': [{'exercise_id': 'ex-0', 'outcome': 'correct'}]})
            restored = (await c.client.get(path, headers=headers())).json()
            assert restored['state'] == 'draft' and restored['result'] is None
            assert restored['answer_hash'] != restored['graded_answer_hash'] and restored['answers'] == edited['answers']
            await c.client.put(path, headers=headers(), json=first)
            restored = (await c.client.get(path, headers=headers())).json()
            assert restored['state'] == 'complete' and restored['result']['items'][0]['outcome'] == 'correct'
    asyncio.run(scenario())


@pytest.mark.parametrize('indexed', [True, False])
def test_exercise_101_and_ownership(tmp_path, indexed):
    async def scenario():
        async with application(tmp_path) as c:
            await ready_practice(c, 101, indexed=indexed)
            assert (await c.client.get('/api/writing/task2/review-100/exercises', headers=headers())).status_code == 200
            for subject in ('user_student1', 'user_teacher', 'user_ta'):
                assert (await c.client.post('/api/exercises/ex-100/hint', headers=headers(subject=subject))).status_code == 404
            assert (await c.client.post('/api/exercises/ex-100/hint', headers=headers())).status_code == 200
            answer = await c.client.post('/api/exercises/ex-100/answer', headers=headers(), json={'answer':'a','request_id':'exercise_101_answer'})
            assert answer.status_code == 202
    asyncio.run(scenario())


def test_hint_snapshot_and_historical_hint_order(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            await ready_practice(c, 2)
            path = '/api/exercises/ex-0'
            posted = await c.client.post(path+'/answer', headers=headers(), json={'answer':'a','request_id':'first_answer'})
            job = await claim(c.database, c.settings)
            assert job.payload['hint_snapshot'] == {'ex-0': False}
            await c.client.post(path+'/hint', headers=headers())
            # Completion happens after the hint; eligibility is fixed at submission.
            await Worker(c.database, c.settings, None, None).finish(job, result={'exercise_id':'ex-0','outcome':'correct'})
            progress = (await c.client.get('/api/writing/task2/review-0/progress', headers=headers())).json()
            assert posted.status_code == 202 and progress['unassisted_first_attempt_accuracy'] == 1.0
            async with c.database.transaction() as db:
                stored = await db.get(Job, job.id)
                stored.payload = {'exercise_id':'ex-0','answer':'a'}  # Historical job without snapshot.
            assert (await c.client.get('/api/writing/task2/review-0/progress',headers=headers())).json()['unassisted_first_attempt_accuracy'] == 1.0
            await c.client.post('/api/exercises/ex-1/hint', headers=headers())
            await c.client.post('/api/exercises/ex-1/answer', headers=headers(), json={'answer':'a','request_id':'after_hint_answer'})
            hinted = await claim(c.database, c.settings)
            assert hinted.payload['hint_snapshot'] == {'ex-1': True}
            await Worker(c.database, c.settings, None, None).finish(hinted, result={'exercise_id':'ex-1','outcome':'correct'})
            assert (await c.client.get('/api/writing/task2/review-1/progress',headers=headers())).json()['unassisted_first_attempt_accuracy'] is None
    asyncio.run(scenario())


def test_practice_completion_publishes_direct_lookup_atomically(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            await ready_practice(c, indexed=False)
            async with c.database.transaction() as db:
                db.add(Job(user_id=c.accounts[0].id, submission_id='review-0', kind='practice',
                           request_key='index_generation', fingerprint='offline', payload={}))
            job = await claim(c.database, c.settings)
            payload = {'errors': [], 'exercises': [exercise()]}
            assert await Worker(c.database, c.settings, None, None).finish(job, result=payload)
            async with c.database.sessions() as db:
                assert (await db.get(PracticeExercise, 'ex-0')).submission_id == 'review-0'
                assert (await db.get(PracticeSet, 'review-0')).state == 'ready'
            assert (await c.client.post('/api/exercises/ex-0/hint', headers=headers())).status_code == 200
    asyncio.run(scenario())
