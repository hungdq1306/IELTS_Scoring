"""Atomic admission and leased jobs, independent of the web request lifecycle."""
import time

from fastapi import HTTPException
from sqlalchemy import func, select

from app.guardrails import fingerprint
from app.models import Job, PracticeSet, QuotaBucket, Submission, uid


async def locked_bucket(session, key):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = sqlite_insert if session.bind.dialect.name == 'sqlite' else pg_insert
    await session.execute(insert(QuotaBucket).values(key=key, events=[]).on_conflict_do_nothing(index_elements=['key']))
    return await session.scalar(select(QuotaBucket).where(QuotaBucket.key == key).with_for_update())


async def consume_quota(session, key, limit, seconds=86400):
    bucket = await locked_bucket(session, key)
    now = time.time()
    events = [value for value in bucket.events if value > now - seconds]
    if len(events) >= limit:
        retry = max(1, int(events[0] + seconds - now) + 1)
        raise HTTPException(429, 'Bạn đã hết lượt sử dụng trong khoảng thời gian này. Vui lòng thử lại sau.',
                            headers={'Retry-After': str(retry)})
    bucket.events = [*events, now]


async def find_request(session, user_id, kind, key, payload):
    prior = await session.scalar(select(Job).where(Job.user_id == user_id, Job.kind == kind, Job.request_key == key))
    if prior and prior.fingerprint != fingerprint(payload):
        raise HTTPException(409, 'Mã yêu cầu này đã được dùng cho nội dung khác.')
    return prior


async def enqueue(session, settings, user_id, submission_id, kind, key, payload):
    # All writers take the admission lock before checking backlog; there is no COUNT/INSERT race.
    await locked_bucket(session, 'queue-admission')
    backlog = await session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['QUEUED', 'RUNNING'])))
    if backlog >= settings.max_queued_jobs:
        raise HTTPException(503, 'Hàng đợi đang đầy. Bài viết của bạn vẫn được giữ trên trình duyệt.', headers={'Retry-After': '30'})
    job = Job(user_id=user_id, submission_id=submission_id, kind=kind, request_key=key,
              fingerprint=fingerprint(payload), payload=payload, priority=0 if kind == 'score' else 10)
    session.add(job)
    await session.flush()
    return job


async def claim(database, settings):
    async with database.transaction() as session:
        now = time.time()
        stale = list((await session.scalars(select(Job).where(Job.status == 'RUNNING', Job.lease_expires_at < now)
                                             .order_by(Job.id).with_for_update(skip_locked=True).limit(20))).all())
        for job in stale:
            job.status = 'FAILED' if job.attempt_count >= settings.job_max_attempts else 'QUEUED'
            job.lease_token = None
            job.lease_expires_at = None
            job.error_code = 'worker_interrupted'
            if job.kind == 'score':
                submission = await session.get(Submission, job.submission_id)
                submission.status = 'FAILED' if job.status == 'FAILED' else 'QUEUED'
            elif job.kind == 'practice' and job.status == 'FAILED':
                practice = await session.get(PracticeSet, job.submission_id)
                if practice: practice.state = 'failed'
        await session.flush()
        job = await session.scalar(select(Job).where(Job.status == 'QUEUED', Job.next_attempt_at <= now)
                                   .order_by(Job.priority, Job.created_at, Job.id)
                                   .with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        job.status, job.lease_token = 'RUNNING', uid()
        job.attempt_count += 1
        job.lease_expires_at = now + settings.worker_lease_seconds
        if job.kind == 'score':
            (await session.get(Submission, job.submission_id)).status = 'SCORING'
        await session.flush()
        return job


def ticket(job):
    return {'job_id': job.id, 'submission_id': job.submission_id, 'status': job.status,
            'poll_url': '/api/jobs/' + job.id}
