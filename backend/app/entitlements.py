"""Calendar-day credits; callers serialize admission before counting submissions."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import math

from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import User, ClassRoom, Membership, Submission, SystemSetting

DEFAULTS = dict(enrolled_student_daily_limit=3, ta_daily_limit=5, teacher_daily_limit=20,
                admin_daily_limit=50, global_daily_submission_cap=500,
                calibration_offsets_json={'tr': 0.0, 'cc': 0.0, 'lr': 0.0, 'gra': 0.0},
                active_prompt_version='v2', model_prices_usd_per_million={})


async def system_settings(session):
    row = await session.get(SystemSetting, 'pilot')
    return {**DEFAULTS, **(row.value if row else {})}


def vn_day(now=None):
    local = datetime.fromtimestamp(time.time() if now is None else now, ZoneInfo('Asia/Ho_Chi_Minh'))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), (start + timedelta(days=1)).isoformat()


async def get_user_quota_status(user, db, now=None):
    # Refresh inside the transaction: role changes cannot be supplied by clients.
    user = await db.get(User, user.id, populate_existing=True)
    if not user.active:
        raise HTTPException(403, 'Account is suspended.')
    rooms = list((await db.scalars(select(ClassRoom).join(Membership, Membership.class_id == ClassRoom.id)
        .where(Membership.user_id == user.id, Membership.active.is_(True), ClassRoom.active.is_(True)))).all())
    config = await system_settings(db)
    start, reset = vn_day(now)
    used = await db.scalar(select(func.count()).select_from(Submission).where(
        Submission.user_id == user.id, func.coalesce(Submission.credit_reserved_at,Submission.created_at) >= start, Submission.status != 'FAILED'))
    if user.role == 'student':
        limit = max((r.daily_student_quota for r in rooms), default=0) + (user.bonus_daily_credits if rooms else 0)
    else:
        limit = config[user.role + '_daily_limit'] + (user.bonus_daily_credits if user.role != 'admin' else 0)
    return {'role': user.role, 'is_enrolled': bool(rooms), 'daily_limit': limit,
            'used_today': used, 'remaining_today': max(0, limit-used), 'reset_at_vn': reset,
            'classes': [{'id': r.id, 'name': r.name} for r in rooms]}


async def admit_grading(session, user, *, retry=False):
    from app.queue import locked_bucket
    # A single order (global then user) serializes concurrent COUNT+INSERT admissions.
    await locked_bucket(session, 'grading-admission')
    status = await get_user_quota_status(user, session)
    if status['role'] == 'student' and not status['is_enrolled']:
        raise HTTPException(403, {'code': 'CLASS_ENROLLMENT_REQUIRED', 'message':
            'Bạn cần tham gia lớp học bằng mã lớp của giảng viên để mở khóa 3 lượt chấm điểm mỗi ngày.'})
    if status['remaining_today'] <= 0:
        retry = max(1, math.ceil(datetime.fromisoformat(status['reset_at_vn']).timestamp()-time.time()))
        raise HTTPException(429, {'code': 'DAILY_QUOTA_EXCEEDED', 'message': 'Bạn đã hết lượt chấm hôm nay.', 'reset_at_vn': status['reset_at_vn']}, headers={'Retry-After': str(retry)})
    start, _ = vn_day()
    # Count ALL admissions globally, including failed jobs, to bound provider costs.
    total = await session.scalar(select(func.count()).select_from(Submission).where(Submission.created_at >= start))
    # Retries reuse a submission, so their additional admissions need a separate ledger.
    # The global lock above also serializes this counter with ordinary submissions.
    retries = await locked_bucket(session, 'grading-retry-admissions')
    events = [at for at in retries.events if at >= start]
    if total + len(events) >= (await system_settings(session))['global_daily_submission_cap']:
        raise HTTPException(429, {'code': 'GLOBAL_DAILY_CAP', 'message': 'Hệ thống đã đạt giới hạn chấm trong ngày.'})
    if retry:
        retries.events = [*events, time.time()]
    return status
