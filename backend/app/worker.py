import asyncio
import logging
import random
import time
from contextlib import suppress

from pydantic import ValidationError
from sqlalchemy import select, update

from app.guardrails import redact_pii
from app.models import Assessment, Job, PracticeSet, Submission
from app.practice.prompts import ANSWER_EVALUATOR
from app.practice.schemas import AnswerAssessment
from app.providers.base import ProviderError
from app.queue import claim
from app.services import drill_gen, scorer

log = logging.getLogger('fogwrite.worker')


class LostLease(Exception):
    pass


class Worker:
    def __init__(self, database, settings, provider, answer_provider, handler=None):
        self.database, self.settings = database, settings
        self.provider, self.answer_provider = provider, answer_provider
        self.handler = handler or self.execute
        self.last_heartbeat = time.time()

    async def execute(self, job):
        async with self.database.sessions() as session:
            submission = await session.get(Submission, job.submission_id)
            assessment = await session.get(Assessment, job.submission_id)
            practice = await session.get(PracticeSet, job.submission_id)
        # All database sessions are CLOSED before LLM calls.
        if job.kind == 'score':
            return await scorer.score(submission, self.provider)
        if job.kind == 'practice':
            return await drill_gen.generate(submission, assessment.result, practice.templates,
                                            self.provider, self.settings.practice_items_per_set)
        if job.kind == 'answer':
            exercise = next(row for row in practice.payload['exercises'] if row['exercise_id'] == job.payload['exercise_id'])
            return await drill_gen.evaluate_answer(exercise, job.payload['answer'], self.answer_provider, job.id)
        if job.kind == 'practice_batch':
            result = await drill_gen.evaluate_batch(practice.payload['exercises'], job.payload['answers'], self.answer_provider, job.id)
            result['submission_id'] = submission.id
            return result
        if job.kind == 'revision':
            assessment = await drill_gen.structured(self.answer_provider, ANSWER_EVALUATOR,
                {key: redact_pii(value) if isinstance(value, str) else value for key, value in job.payload.items() if key != 'request_id'}, AnswerAssessment)
            data = assessment.model_dump()
            if data['outcome'] == 'correct' and not all(data[key] for key in ('target_fixed', 'meaning_preserved', 'no_new_serious_errors')):
                data['outcome'] = 'partially_correct'
            return {**job.payload, 'revision_id': job.id, 'state': 'complete', 'feedback': data, 'human_reviewed': False}
        raise ValueError('Unsupported job kind')

    async def heartbeat(self, job):
        while True:
            await asyncio.sleep(self.settings.worker_lease_seconds / 3)
            now = time.time()
            async with self.database.transaction() as session:
                changed = await session.execute(update(Job).where(Job.id == job.id, Job.status == 'RUNNING',
                    Job.lease_token == job.lease_token, Job.lease_expires_at > now)
                    .values(lease_expires_at=now + self.settings.worker_lease_seconds))
                if changed.rowcount != 1:
                    raise LostLease()

    async def finish(self, job, result=None, error=None):
        async with self.database.transaction() as session:
            stored = await session.scalar(select(Job).where(Job.id == job.id).with_for_update())
            if not stored or stored.status != 'RUNNING' or stored.lease_token != job.lease_token or stored.lease_expires_at <= time.time():
                return False
            submission = await session.get(Submission, job.submission_id)
            if error:
                code = error.code if isinstance(error, ProviderError) else 'invalid_output' if isinstance(error, (ValidationError, ValueError)) else 'worker_error'
                retryable = (isinstance(error, ProviderError) and error.retryable) or isinstance(error, (TimeoutError, ValidationError, ValueError))
                stored.error_code = code
                retry = retryable and stored.attempt_count < self.settings.job_max_attempts
                stored.status = 'QUEUED' if retry else 'FAILED'
                stored.next_attempt_at = time.time() + max(getattr(error, 'retry_after', 0) or 0, 5 * 2 ** stored.attempt_count + random.uniform(0, 1))
                if job.kind == 'score':
                    submission.status = 'QUEUED' if retry else 'FAILED'
                if job.kind == 'practice':
                    (await session.get(PracticeSet, job.submission_id)).state = 'generating' if retry else 'failed'
                log.warning('job_failed job=%s kind=%s code=%s retry=%s', job.id, job.kind, code, retry)
            else:
                stored.status, stored.completed_at, stored.error_code = 'COMPLETED', time.time(), None
                stored.result = result
                if job.kind == 'score':
                    session.add(Assessment(submission_id=job.submission_id, result=result, raw_scores=result.get('raw_criterion_scores', result['criterion_scores'])))
                    submission.status = 'COMPLETED'
                elif job.kind == 'practice':
                    practice = await session.get(PracticeSet, job.submission_id)
                    practice.state, practice.payload = 'ready', result
                    stored.result = drill_gen.public_practice(job.submission_id, 'ready', result)
            stored.lease_token, stored.lease_expires_at = None, None
            return True

    async def process(self, job):
        operation = asyncio.create_task(self.handler(job))
        heartbeat = asyncio.create_task(self.heartbeat(job))
        try:
            async with asyncio.timeout(self.settings.job_timeout_seconds):
                done, _ = await asyncio.wait([operation, heartbeat], return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    heartbeat.result()
                    raise LostLease()
                await self.finish(job, result=operation.result())
        except LostLease:
            pass
        except asyncio.CancelledError:
            raise  # Lease expiry recovers unfinished jobs; never mark a cancellation successful.
        except Exception as error:
            await self.finish(job, error=error)
        finally:
            for task in (operation, heartbeat):
                task.cancel()
            await asyncio.gather(operation, heartbeat, return_exceptions=True)

    async def run(self):
        while True:
            self.last_heartbeat = time.time()
            try:
                job = await claim(self.database, self.settings)
                if job:
                    await self.process(job)
                else:
                    await asyncio.sleep(self.settings.worker_poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.error('worker_poll_failed type=%s', type(error).__name__)
                await asyncio.sleep(2)
