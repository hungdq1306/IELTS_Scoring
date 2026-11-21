"""Audited governance; identity always comes from the verified session."""
import math
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import Field, model_validator
from sqlalchemy import select, func
from app.auth import current_user
from app.models import User, ClassRoom, Submission, Job, Assessment, SystemSetting, AuditEvent, ProviderUsage
from app.grading.schemas import StrictModel
from app.entitlements import system_settings, vn_day
from app.queue import locked_bucket

router = APIRouter(prefix='/api/admin')


async def admin_user(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Administrator permissions required.')
    return user


class UserPatch(StrictModel):
    role: Literal['student', 'ta', 'teacher', 'admin'] | None = None
    is_active: bool | None = None
    bonus_daily_credits: int | None = Field(None, ge=0, le=100)


class SettingsPatch(StrictModel):
    enrolled_student_daily_limit: int | None = Field(None, ge=1, le=100)
    ta_daily_limit: int | None = Field(None, ge=1, le=100)
    teacher_daily_limit: int | None = Field(None, ge=1, le=200)
    admin_daily_limit: int | None = Field(None, ge=1, le=500)
    global_daily_submission_cap: int | None = Field(None, ge=1, le=10000)
    active_prompt_version: Literal['v1', 'v2'] | None = None
    calibration_offsets_json: dict[str, float] | None = None
    model_prices_usd_per_million: dict[str, dict[str, float]] | None = None

    @model_validator(mode='after')
    def offsets(self):
        if self.model_prices_usd_per_million is not None:
            for model, prices in self.model_prices_usd_per_million.items():
                if len(model)>120 or set(prices)!={'input','output'} or any(not math.isfinite(v) or v<0 for v in prices.values()):
                    raise ValueError('Each model price requires finite nonnegative input and output USD per million tokens.')
        if self.calibration_offsets_json is not None and any(k not in ('tr','cc','lr','gra') or not math.isfinite(v) or abs(v)>1 for k,v in self.calibration_offsets_json.items()):
            raise ValueError('Calibration requires tr/cc/lr/gra with finite offsets between -1 and 1.')
        return self


def public_user(u):
    return dict(id=u.id, external_auth_id=u.external_auth_id, role=u.role, is_active=u.active, bonus_daily_credits=u.bonus_daily_credits)


@router.get('/users')
async def users(request: Request, q: str = Query('', max_length=200), offset: int = Query(0, ge=0), user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db:
        rows = await db.scalars(select(User).where(User.external_auth_id.contains(q, autoescape=True) | User.id.contains(q, autoescape=True))
            .order_by(User.created_at, User.id).offset(offset).limit(100))
        return {'items': [public_user(u) for u in rows]}


@router.patch('/users/{user_id}')
async def update_user(user_id: str, body: UserPatch, request: Request, user=Depends(admin_user)):
    async with request.app.state.database.transaction() as db:
        await locked_bucket(db, 'admin-governance')
        target = await db.get(User, user_id, populate_existing=True)
        if not target: raise HTTPException(404, 'User not found.')
        if target.role == 'admin' and (body.role not in (None,'admin') or body.is_active is False):
            count = await db.scalar(select(func.count()).select_from(User).where(User.role=='admin', User.active.is_(True)))
            if count <= 1: raise HTTPException(409, 'The last active administrator cannot be removed.')
        before = public_user(target)
        for k,v in body.model_dump(exclude_none=True).items(): setattr(target, 'active' if k=='is_active' else k,v)
        db.add(AuditEvent(actor_id=user.id, action='admin_user_updated',target_id=target.id,detail={'previous':before,'current':public_user(target)}))
        return public_user(target)


@router.get('/settings')
async def settings(request: Request, user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db: return await system_settings(db)


@router.patch('/settings')
async def update_settings(body: SettingsPatch, request: Request, user=Depends(admin_user)):
    async with request.app.state.database.transaction() as db:
        await locked_bucket(db, 'admin-governance')
        values = {**await system_settings(db), **body.model_dump(exclude_none=True)}
        row = await db.get(SystemSetting,'pilot')
        if row: row.value=values
        else: db.add(SystemSetting(key='pilot',value=values))
        if body.enrolled_student_daily_limit is not None:
            # Explicit global policy update applies to active classes.
            from sqlalchemy import update
            await db.execute(update(ClassRoom).where(ClassRoom.active.is_(True)).values(daily_student_quota=body.enrolled_student_daily_limit))
        db.add(AuditEvent(actor_id=user.id,action='system_settings_updated',target_id='pilot',detail=body.model_dump(exclude_none=True)))
        return values


@router.get('/overview')
async def overview(request: Request, user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db:
        roles = dict((await db.execute(select(User.role,func.count()).group_by(User.role))).all())
        today = await db.scalar(select(func.count()).select_from(Submission).where(Submission.created_at>=vn_day()[0]))
        classes = await db.scalar(select(func.count()).select_from(ClassRoom).where(ClassRoom.active.is_(True)))
        queue = await db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['QUEUED','RUNNING'])))
        results = (await db.scalars(select(ProviderUsage))).all()
        config = await system_settings(db)
        tokens, cost, unknown = 0, 0.0, 0
        for r in results:
            usage = r.usage
            tokens += int(usage.get('total_token_count',usage.get('total_tokens',0)))
            price = config.get('model_prices_usd_per_million',{}).get(r.model)
            if price is None or not usage:
                unknown += 1
            else:
                output = usage.get('candidates_token_count',0)+usage.get('thoughts_token_count',0)
                cost += (usage.get('prompt_token_count',0)*price['input']+output*price['output'])/1000000
        return {'users_by_role':roles,'active_classes':classes,'today_submissions':today,'queue_depth':queue,
                'total_tokens_used':tokens,'estimated_gemini_cost':round(cost,6) if not unknown else None,
                'priced_cost_usd':round(cost,6),'unpriced_or_unknown_calls':unknown,'recorded_calls':len(results),
                'usage_scope':'Provider responses since v2 migration, including practice; unavailable upstream usage and crash windows cannot be billed precisely.'}
