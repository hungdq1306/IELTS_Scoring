"""Audited governance; identity always comes from the verified session."""
import math
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import Field, model_validator
from sqlalchemy import select, func, or_, update
from app.auth import current_user
from app.models import User, ClassRoom, Submission, Job, Assessment, SystemSetting, AuditEvent, ProviderUsage, Membership
from app.grading.schemas import StrictModel
from app.entitlements import system_settings, vn_day
from app.queue import locked_bucket
from app.identity import display_label, sync_profile, public_profile
from app.enrollment import change_role

router = APIRouter(prefix='/api/admin')


async def admin_user(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Administrator permissions required.')
    return user


class UserPatch(StrictModel):
    role: Literal['student', 'ta', 'teacher', 'admin'] | None = None
    is_active: bool | None = None
    bonus_daily_credits: int | None = Field(None, ge=0, le=100)
    reason: str = Field('',max_length=1500)


class SettingsPatch(StrictModel):
    apply_to_existing_classes: bool = False
    reason: str = Field('',max_length=1500)
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
    return dict(id=u.id, external_auth_id=u.external_auth_id, role=u.role, is_active=u.active, bonus_daily_credits=u.bonus_daily_credits,
                **public_profile(u))


@router.get('/users')
async def users(request: Request, q: str = Query('', max_length=200), search: str = Query('',max_length=200),
                role: Literal['student','ta','teacher','admin'] | None = None, is_active: bool | None = None,
                class_id: str | None = None, limit: int = Query(25,ge=1,le=100), offset: int = Query(0, ge=0), user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db:
        text=search or q
        filters=[or_(*(field.contains(text,autoescape=True) for field in (User.full_name,User.email,User.reported_full_name,User.reported_email,User.external_auth_id,User.id)))]
        if role:filters.append(User.role==role)
        if is_active is not None:filters.append(User.active==is_active)
        if class_id:filters.append(User.id.in_(select(Membership.user_id).where(Membership.class_id==class_id,Membership.active.is_(True))))
        total=await db.scalar(select(func.count()).select_from(User).where(*filters))
        rows=list((await db.scalars(select(User).where(*filters).order_by(User.created_at,User.id).offset(offset).limit(limit))).all())
        ids=[u.id for u in rows]
        rooms=(await db.execute(select(Membership.user_id,ClassRoom).join(ClassRoom,ClassRoom.id==Membership.class_id)
            .where(Membership.user_id.in_(ids),Membership.active.is_(True),ClassRoom.active.is_(True)))).all()
        used=dict((await db.execute(select(Submission.user_id,func.count()).where(Submission.user_id.in_(ids),
            func.coalesce(Submission.credit_reserved_at,Submission.created_at)>=vn_day()[0],Submission.status!='FAILED').group_by(Submission.user_id))).all())
        config=await system_settings(db)
        items=[]
        for u in rows:
            enrolled=[r for member,r in rooms if member==u.id]
            daily=(max((r.daily_student_quota for r in enrolled),default=0)+(u.bonus_daily_credits if enrolled else 0)) if u.role=='student' else config[u.role+'_daily_limit']+(u.bonus_daily_credits if u.role!='admin' else 0)
            items.append({**public_user(u),'classes':[{'id':r.id,'name':r.name} for r in enrolled],
                          'daily_limit':daily,'used_today':used.get(u.id,0),'remaining_today':max(0,daily-used.get(u.id,0))})
        return {'items':items,'total':total,'limit':limit,'offset':offset}


@router.patch('/users/{user_id}')
async def update_user(user_id: str, body: UserPatch, request: Request, user=Depends(admin_user)):
    async with request.app.state.database.transaction() as db:
        await locked_bucket(db, 'admin-governance')
        target = await db.get(User, user_id, populate_existing=True)
        if not target: raise HTTPException(404, 'User not found.')
        if target.id==user.id and (body.role not in (None,'admin') or body.is_active is False):
            raise HTTPException(409,'You cannot demote or deactivate your current administrator account.')
        if target.role == 'admin' and (body.role not in (None,'admin') or body.is_active is False):
            count = await db.scalar(select(func.count()).select_from(User).where(User.role=='admin', User.active.is_(True)))
            if count <= 1: raise HTTPException(409, 'The last active administrator cannot be removed.')
        before = public_user(target)
        if body.role is not None and body.role != target.role:
            await change_role(db, target, body.role)
        for k,v in body.model_dump(exclude_none=True,exclude={'reason'}).items(): setattr(target, 'active' if k=='is_active' else k,v)
        db.add(AuditEvent(actor_id=user.id, action='admin_user_updated',target_id=target.id,detail={'previous':before,'current':public_user(target),'reason':body.reason}))
        return public_user(target)


@router.get('/settings')
async def settings(request: Request, user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db: return await system_settings(db)


@router.patch('/settings')
async def update_settings(body: SettingsPatch, request: Request, user=Depends(admin_user)):
    async with request.app.state.database.transaction() as db:
        await locked_bucket(db, 'admin-governance')
        before=await system_settings(db)
        changes=body.model_dump(exclude_none=True,exclude={'apply_to_existing_classes','reason'})
        values = {**before, **changes}
        row = await db.get(SystemSetting,'pilot')
        if row: row.value=values
        else: db.add(SystemSetting(key='pilot',value=values))
        affected=0
        if body.apply_to_existing_classes:
            result=await db.execute(update(ClassRoom).where(ClassRoom.active.is_(True)).values(daily_student_quota=values['enrolled_student_daily_limit']))
            affected=result.rowcount
        db.add(AuditEvent(actor_id=user.id,action='system_settings_updated',target_id='pilot',detail={'previous':before,'current':values,'reason':body.reason,'affected_classes_count':affected}))
        return {'settings':values,'affected_classes_count':affected}


@router.get('/overview')
async def overview(request: Request, user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db:
        roles = dict((await db.execute(select(User.role,func.count()).group_by(User.role))).all())
        today = await db.scalar(select(func.count()).select_from(Submission).where(Submission.created_at>=vn_day()[0]))
        classes = await db.scalar(select(func.count()).select_from(ClassRoom).where(ClassRoom.active.is_(True)))
        queue = await db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['QUEUED','RUNNING'])))
        now=time.time()
        results = (await db.scalars(select(ProviderUsage).where(ProviderUsage.created_at>=now-7*86400))).all()
        config = await system_settings(db)
        prices = config.get('model_prices_usd_per_million', {})
        has_pricing = bool(prices)
        tokens, cost, unknown = 0, 0.0, 0
        breakdown={}
        for r in results:
            usage = r.usage
            from datetime import datetime
            from zoneinfo import ZoneInfo
            group=(datetime.fromtimestamp(r.created_at,ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat(),r.model)
            summary=breakdown.setdefault(group,{'day':group[0],'model':group[1],'tokens':0,'cost_usd':0.0,'unknown_calls':0,'calls':0})
            summary['calls']+=1
            summary['tokens']+=int(usage.get('total_token_count',usage.get('total_tokens',0)))
            tokens += int(usage.get('total_token_count',usage.get('total_tokens',0)))
            price = prices.get(r.model)
            if price is None or not usage:
                unknown += 1
                summary['unknown_calls']+=1
            else:
                output = usage.get('candidates_token_count',0)+usage.get('thoughts_token_count',0)
                cost += (usage.get('prompt_token_count',0)*price['input']+output*price['output'])/1000000
                summary['cost_usd']+=(usage.get('prompt_token_count',0)*price['input']+output*price['output'])/1000000
        for summary in breakdown.values():
            summary['pricing_status']='Pricing unconfigured' if summary['model'] not in prices else 'Usage unavailable' if summary['unknown_calls'] else 'Configured'
            summary['cost_usd']=None if summary['unknown_calls'] else round(summary['cost_usd'],6)
        completed=await db.scalar(select(func.count()).select_from(Submission).where(Submission.created_at>=vn_day()[0],Submission.status=='COMPLETED'))
        failed=await db.scalar(select(func.count()).select_from(Job).where(Job.status=='FAILED',func.coalesce(Job.completed_at,Job.created_at)>=vn_day()[0]))
        oldest=await db.scalar(select(func.min(Job.created_at)).where(Job.status.in_(['QUEUED','RUNNING'])))
        latency_rows=(await db.execute(select(Job.completed_at,Assessment.result).join(Assessment,Assessment.submission_id==Job.submission_id)
            .where(Job.kind=='score',Job.status=='COMPLETED',Job.completed_at>=now-7*86400))).all()
        latency={}
        for window,seconds in [('24h',86400),('7d',7*86400)]:
            values=sorted(row.get('latency_ms',0)/1000 for at,row in latency_rows if at>=now-seconds and row.get('latency_ms') is not None)
            latency[window]={'count':len(values),'median_sec':percentile(values,.5),'p95_sec':percentile(values,.95)}
        return {'users_by_role':roles,'active_classes':classes,'today_submissions':today,'queue_depth':queue,
                'completed_today':completed,'failed_jobs_today':failed,'longest_active_wait_sec':round(max(0,now-oldest)) if oldest else 0,
                'grading_latency':latency,'usage_by_day_model':list(breakdown.values()),
                'total_tokens_used':tokens,'pricing_configured':has_pricing,
                'estimated_gemini_cost':round(cost,6) if (has_pricing and not unknown) else None,
                'priced_cost_usd':round(cost,6),'unpriced_or_unknown_calls':unknown,'recorded_calls':len(results),
                'usage_scope':'Provider responses since v2 migration, including practice; unavailable upstream usage and crash windows cannot be billed precisely.'}


def percentile(values,p):
    if not values:return None
    at=(len(values)-1)*p
    low=int(at);high=min(low+1,len(values)-1)
    return round(values[low]+(values[high]-values[low])*(at-low),3)


def job_label(job):
    if job.status=='COMPLETED':return 'DONE'
    if job.status=='RUNNING':return 'SCORING' if job.kind=='score' else 'GENERATING_PRACTICE'
    return job.status


@router.get('/jobs')
async def jobs(request: Request, status: Literal['QUEUED','SCORING','GENERATING_PRACTICE','FAILED','DONE'] | None=None,
               search: str=Query('',max_length=200),limit: int=Query(25,ge=1,le=100),offset: int=Query(0,ge=0),user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db:
        filters=[or_(User.full_name.contains(search,autoescape=True),User.email.contains(search,autoescape=True),User.reported_full_name.contains(search,autoescape=True),User.reported_email.contains(search,autoescape=True),User.external_auth_id.contains(search,autoescape=True),Submission.id.contains(search,autoescape=True))]
        if status in ('QUEUED','FAILED'):filters.append(Job.status==status)
        elif status=='DONE':filters.append(Job.status=='COMPLETED')
        elif status=='SCORING':filters.extend([Job.status=='RUNNING',Job.kind=='score'])
        elif status=='GENERATING_PRACTICE':filters.extend([Job.status=='RUNNING',Job.kind!='score'])
        query=select(Job,Submission,User,ClassRoom).join(Submission,Submission.id==Job.submission_id).join(User,User.id==Job.user_id).join(ClassRoom,ClassRoom.id==Submission.class_id).where(*filters)
        total=await db.scalar(select(func.count()).select_from(query.subquery()))
        rows=(await db.execute(query.order_by(Job.created_at.desc(),Job.id).offset(offset).limit(limit))).all()
        return {'items':[{'job_id':j.id,'submission_id':s.id,'submission_code':s.id[:8].upper(),'student_name':display_label(u),
            'student_email':public_profile(u)['email'],'email_source':public_profile(u)['email_source'],'class_name':c.name,'kind':j.kind,'status':job_label(j),'attempt_count':j.attempt_count,
            'created_at':j.created_at,'completed_at':j.completed_at,'wait_duration_sec':round(max(0,(j.completed_at or time.time())-j.created_at)),
            'error_code':j.error_code,'error_message':'The AI operation failed. Review the error code before retrying.' if j.error_code else None,
            'credit_refunded':j.kind=='score' and j.status=='FAILED' and s.status=='FAILED'} for j,s,u,c in rows],
            'total':total,'limit':limit,'offset':offset}


class RetryInput(StrictModel):
    reason: str = Field('',max_length=1500)


@router.post('/jobs/{submission_id}/retry')
async def retry_job(submission_id: str, body: RetryInput, request: Request,user=Depends(admin_user)):
    from app.entitlements import admit_grading
    from app.queue import ticket, consume_quota, ensure_queue_capacity
    async with request.app.state.database.transaction() as db:
        submission=await db.get(Submission,submission_id)
        if not submission:raise HTTPException(404,'Submission not found.')
        await locked_bucket(db,'submit:'+submission.user_id)
        job=await db.scalar(select(Job).where(Job.submission_id==submission_id,Job.kind=='score').with_for_update())
        if await db.get(Assessment,submission_id):raise HTTPException(409,'An assessment already exists; scoring cannot be repeated.')
        if not job:raise HTTPException(404,'Scoring job not found.')
        if job.status in ('QUEUED','RUNNING'):return {**ticket(job),'already_queued':True}
        if job.status!='FAILED':raise HTTPException(409,'Only failed scoring jobs can be retried.')
        owner=await db.get(User,submission.user_id)
        active=await db.scalar(select(Membership.id).join(ClassRoom,ClassRoom.id==Membership.class_id).where(
            Membership.user_id==owner.id,Membership.class_id==submission.class_id,Membership.active.is_(True),ClassRoom.active.is_(True)))
        if not active:raise HTTPException(409,'The student is no longer active in this class.')
        await admit_grading(db,owner,retry=True)
        await ensure_queue_capacity(db,request.app.state.settings)
        await consume_quota(db,'operator-retry:'+submission_id,3)
        before={'status':job.status,'attempt_count':job.attempt_count,'error_code':job.error_code}
        job.status='QUEUED';job.attempt_count=0;job.error_code=None;job.result=None
        job.lease_token=None;job.lease_expires_at=None;job.next_attempt_at=0;job.completed_at=None
        submission.status='QUEUED';submission.credit_reserved_at=time.time()
        db.add(AuditEvent(actor_id=user.id,action='job_retried',target_id=submission_id,
            detail={'previous':before,'current':{'status':'QUEUED','attempt_count':0},'reason':body.reason}))
        return {**ticket(job),'already_queued':False}


@router.get('/audit-logs')
async def audit_logs(request: Request,actor: str=Query('',max_length=200),target: str=Query('',max_length=200),action: str=Query('',max_length=80),
                     limit: int=Query(25,ge=1,le=100),offset: int=Query(0,ge=0),user=Depends(admin_user)):
    async with request.app.state.database.sessions() as db:
        filters=[or_(User.full_name.contains(actor,autoescape=True),User.email.contains(actor,autoescape=True),User.reported_full_name.contains(actor,autoescape=True),User.reported_email.contains(actor,autoescape=True),User.id.contains(actor,autoescape=True)),
                 (AuditEvent.action==action) if action else True]
        if target:
            matching_users=select(User.id).where(or_(User.full_name.contains(target,autoescape=True),User.email.contains(target,autoescape=True),User.reported_full_name.contains(target,autoescape=True),User.reported_email.contains(target,autoescape=True)))
            matching_rooms=select(ClassRoom.id).where(ClassRoom.name.contains(target,autoescape=True))
            filters.append(or_(AuditEvent.target_id.contains(target,autoescape=True),AuditEvent.target_id.in_(matching_users),AuditEvent.target_id.in_(matching_rooms)))
        query=select(AuditEvent,User).join(User,User.id==AuditEvent.actor_id).where(*filters)
        total=await db.scalar(select(func.count()).select_from(query.subquery()))
        rows=(await db.execute(query.order_by(AuditEvent.created_at.desc(),AuditEvent.id).offset(offset).limit(limit))).all()
        items=[]
        for event,actor_user in rows:
            label=event.target_id
            target_user=await db.get(User,event.target_id)
            if target_user:label=display_label(target_user)
            elif room:=await db.get(ClassRoom,event.target_id):label=room.name
            before=event.detail.get('previous',{})
            after=event.detail.get('current',event.detail)
            items.append({'id':event.id,'actor_name':display_label(actor_user),'actor_email':public_profile(actor_user)['email'],'email_source':public_profile(actor_user)['email_source'],
                'target_label':label,'target_id':event.target_id,'action_type':event.action,'before_json':before,'after_json':after,
                'reason':event.detail.get('reason') or (after.get('reason','') if isinstance(after,dict) else ''),'created_at':event.created_at})
        return {'items':items,'total':total,'limit':limit,'offset':offset}


@router.post('/users/sync-profiles')
async def sync_users(request: Request,user=Depends(admin_user)):
    settings=request.app.state.settings
    if not settings.clerk_secret_key.get_secret_value():return {'attempted':0,'note':'CLERK_SECRET_KEY is not configured; display profiles sync on sign-in and remain self-reported until verified.'}
    async with request.app.state.database.sessions() as db:
        rows=list((await db.scalars(select(User).order_by(User.profile_synced_at.asc().nullsfirst()).limit(25))).all())
    for row in rows:await sync_profile(request.app.state.database,row,{},settings,force=True)
    async with request.app.state.database.transaction() as db:
        db.add(AuditEvent(actor_id=user.id,action='profiles_sync_requested',target_id='users',detail={'attempted':len(rows)}))
    return {'attempted':len(rows),'note':'Profiles unavailable from Clerk retain their current display fallback.'}
