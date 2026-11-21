"""Serialized enrollment policy shared by invitations, staff actions and role changes."""
import math
import time
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models import User, Membership, ClassRoom
from app.queue import locked_bucket


def conflict(room):
    raise HTTPException(409, {'code': 'ALREADY_IN_CLASS', 'current_class_id': room.id,
        'current_class_name': room.name,
        'message': f'You are currently enrolled in {room.name}. Please leave {room.name} before joining another class.'})


async def lock_student(db, user_id):
    await locked_bucket(db, 'class-enrollment:' + user_id)
    return await db.get(User, user_id, populate_existing=True)


async def check_join(db, user, target, membership=None, *, staff_override=False):
    if user.role != 'student':
        return
    current = await db.scalar(select(ClassRoom).join(Membership, Membership.class_id == ClassRoom.id)
        .where(Membership.user_id == user.id, Membership.active.is_(True), Membership.class_id != target.id))
    if current:
        conflict(current)
    if membership and membership.active:
        return  # Repeating a current enrollment is idempotent.
    if membership and membership.removed_at is not None and not staff_override:
        raise HTTPException(403, {'code': 'REMOVED_FROM_CLASS', 'message':
            'You were removed from this class by the teacher and cannot rejoin using an invite code.'})
    if staff_override:
        return  # A teacher may explicitly reinstate, but cannot create a second active enrollment.
    prior = list((await db.scalars(select(Membership).where(Membership.user_id == user.id))).all())
    last = max((at for m in prior for at in (m.left_at, m.removed_at) if at is not None), default=0)
    available = last + 86400
    if available > time.time():
        retry = math.ceil(available-time.time())
        raise HTTPException(429, {'code': 'CLASS_SWITCH_COOLDOWN', 'retry_after_seconds': retry,
            'available_at': datetime.fromtimestamp(available, timezone.utc).isoformat(),
            'message': 'You recently left a class. You can join another class after the 24-hour cooldown.'},
            headers={'Retry-After': str(retry)})


def member_role(role):
    return 'student' if role == 'student' else 'ta' if role == 'ta' else 'teacher'


async def change_role(db, user, role):
    await lock_student(db, user.id)
    rows = list((await db.scalars(select(Membership).where(Membership.user_id == user.id))).all())
    if role == 'student' and sum(m.active for m in rows) > 1:
        raise HTTPException(409, {'code':'MULTIPLE_ACTIVE_CLASSES',
            'message':'Resolve active memberships before changing this account to student.'})
    for row in rows:
        if role == 'student' or row.role == 'student':
            row.role = member_role(role)
    user.role = role
