import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.auth import staff_user
from app.grading.schemas import CRITERIA
from app.grading.task2 import overall_band
from app.guardrails import redact_pii
from app.models import Assessment, AuditEvent, ClassRoom, ExerciseTemplate, Membership, Prompt, Submission, TeacherAnchor, TeacherProfile, User, uid
from app.pilot_schemas import AnchorInput, AssignMember, CreateClass, ProfileUpdate, PromptInput, ScoreOverride, TemplateInput
from app.queue import locked_bucket
from app.routers.pilot import class_access, database, effective_grade

router = APIRouter(prefix='/api/teacher')


def teacher_only(user):
    if user.role not in ('teacher', 'admin'):
        raise HTTPException(403, 'Teacher permissions required.')


@router.get('/classes')
async def classes(request: Request, user=Depends(staff_user)):
    async with database(request).sessions() as session:
        query = select(ClassRoom)
        if user.role != 'admin':
            query = query.where((ClassRoom.teacher_id == user.id) | ClassRoom.id.in_(
                select(Membership.class_id).where(Membership.user_id == user.id, Membership.role == 'ta', Membership.active.is_(True))))
        rows = (await session.scalars(query.order_by(ClassRoom.created_at.desc()).limit(100))).all()
        return {'items': [{'id': row.id, 'name': row.name, 'active': row.active, 'invite_uses': row.invite_uses} for row in rows]}


@router.post('/classes', status_code=201)
async def create_class(body: CreateClass, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    code = secrets.token_urlsafe(24)
    async with database(request).transaction() as session:
        classroom = ClassRoom(name=body.name, teacher_id=user.id, invite_hash=hashlib.sha256(code.encode()).hexdigest(),
                              invite_expires_at=time.time() + body.invite_days * 86400, invite_max_uses=body.invite_max_uses)
        session.add(classroom)
        await session.flush()
        session.add(Membership(class_id=classroom.id, user_id=user.id, role='teacher'))
        session.add(AuditEvent(actor_id=user.id, action='class_created', target_id=classroom.id))
        return {'id': classroom.id, 'name': classroom.name, 'join_code': code, 'invite_expires_at': classroom.invite_expires_at}


@router.post('/classes/{class_id}/rotate-invite')
async def rotate(class_id: str, request: Request, user=Depends(staff_user)):
    code = secrets.token_urlsafe(24)
    async with database(request).transaction() as session:
        classroom = await class_access(session, class_id, user, manage=True)
        classroom.invite_hash, classroom.invite_expires_at = hashlib.sha256(code.encode()).hexdigest(), time.time() + 7 * 86400
        classroom.invite_uses = 0
        session.add(AuditEvent(actor_id=user.id, action='invite_rotated', target_id=class_id))
    return {'join_code': code}


@router.get('/classes/{class_id}/members')
async def members(class_id: str, request: Request, user=Depends(staff_user)):
    async with database(request).sessions() as session:
        await class_access(session, class_id, user)
        rows = (await session.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.class_id == class_id).limit(100))).all()
        return {'items': [{'user_id': member.user_id, 'role': member.role, 'active': member.active} for member, account in rows]}


@router.put('/classes/{class_id}/members')
async def assign(class_id: str, body: AssignMember, request: Request, user=Depends(staff_user)):
    async with database(request).transaction() as session:
        await locked_bucket(session, 'membership:' + class_id)
        classroom = await class_access(session, class_id, user, manage=True)
        account = await session.get(User, body.user_id)
        if not account or body.user_id == classroom.teacher_id:
            raise HTTPException(422, 'Choose an existing student/TA account; the class owner cannot be changed here.')
        if body.role == 'ta' and account.role not in ('ta', 'teacher', 'admin'):
            raise HTTPException(422, 'Grant staff role through the trusted admin CLI first.')
        membership = await session.scalar(select(Membership).where(Membership.class_id == class_id, Membership.user_id == body.user_id))
        if not membership:
            membership = Membership(class_id=class_id, user_id=body.user_id)
            session.add(membership)
        membership.role, membership.active = body.role, body.active
        session.add(AuditEvent(actor_id=user.id, action='membership_updated', target_id=body.user_id,
                               detail={'class_id': class_id, 'role': body.role, 'active': body.active}))
    return {'saved': True}


@router.get('/classes/{class_id}/submissions')
async def submissions(class_id: str, request: Request, user=Depends(staff_user)):
    async with database(request).sessions() as session:
        await class_access(session, class_id, user)
        rows = (await session.execute(select(Submission, Assessment).outerjoin(Assessment, Assessment.submission_id == Submission.id)
            .where(Submission.class_id == class_id).order_by(Submission.created_at.desc()).limit(100))).all()
        return {'items': [{'id': submission.id, 'user_id': submission.user_id, 'prompt': submission.prompt,
                           'essay': submission.essay, 'status': submission.status,
                           'grade': effective_grade(assessment) if assessment else None} for submission, assessment in rows]}


@router.put('/submissions/{submission_id}/override')
async def override(submission_id: str, body: ScoreOverride, request: Request, user=Depends(staff_user)):
    async with database(request).transaction() as session:
        submission = await session.get(Submission, submission_id)
        if not submission:
            raise HTTPException(404, 'Submission not found.')
        await class_access(session, submission.class_id, user, manage=True)
        assessment = await session.get(Assessment, submission_id)
        if not assessment:
            raise HTTPException(409, 'Wait for assessment completion.')
        previous = assessment.teacher_override
        assessment.teacher_override = {'scores': body.scores.model_dump(), 'overall': overall_band(body.scores), 'reason': body.reason, 'at': time.time()}
        assessment.reviewed_by = user.id
        session.add(AuditEvent(actor_id=user.id, action='score_override', target_id=submission_id,
                               detail={'previous': previous, 'current': assessment.teacher_override}))
    return {'saved': True, 'overall': overall_band(body.scores)}


@router.put('/profile')
async def profile(body: ProfileUpdate, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    if any(key not in CRITERIA or not -1 <= value <= 1 for key, value in body.offsets.items()):
        raise HTTPException(422, 'Offsets require known criterion names and finite values between -1 and 1.')
    async with database(request).transaction() as session:
        await locked_bucket(session, 'profile:' + user.id)
        row = await session.get(TeacherProfile, user.id)
        if row is None:
            row = TeacherProfile(teacher_id=user.id, version=0)
            session.add(row)
        row.version += 1
        row.style, row.offsets = redact_pii(body.style), body.offsets
        session.add(AuditEvent(actor_id=user.id, action='profile_updated', target_id=user.id, detail={'version': row.version}))
    return {'version': row.version}


@router.get('/anchors')
async def anchors(request: Request, user=Depends(staff_user)):
    teacher_only(user)
    async with database(request).sessions() as session:
        rows = (await session.scalars(select(TeacherAnchor).where((TeacherAnchor.teacher_id == user.id) | TeacherAnchor.teacher_id.is_(None)).order_by(TeacherAnchor.id).limit(100))).all()
        return {'items': [{'id': row.id, 'version': row.version, 'active': row.active, 'default': row.teacher_id is None, 'payload': row.payload} for row in rows]}


@router.post('/anchors', status_code=201)
async def add_anchor(body: AnchorInput, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    key = uid()
    async with database(request).transaction() as session:
        session.add(TeacherAnchor(id=key, teacher_id=user.id,
            payload={'essay_id': key, 'question': redact_pii(body.prompt), 'student_essay': redact_pii(body.essay),
                     'scores': {**body.scores.model_dump(), 'overall': overall_band(body.scores)},
                     'examiner_calibration_cue': 'Teacher-uploaded calibration anchor; not independently examiner verified.'}))
        session.add(AuditEvent(actor_id=user.id, action='anchor_added', target_id=key))
    return {'id': key}


@router.delete('/anchors/{anchor_id}')
async def remove_anchor(anchor_id: str, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    async with database(request).transaction() as session:
        row = await session.get(TeacherAnchor, anchor_id)
        if not row or row.teacher_id != user.id:
            raise HTTPException(404, 'Anchor not found.')
        row.active = False
        session.add(AuditEvent(actor_id=user.id, action='anchor_disabled', target_id=anchor_id))
    return {'saved': True}


@router.get('/templates')
async def templates(request: Request, user=Depends(staff_user)):
    teacher_only(user)
    async with database(request).sessions() as session:
        rows = (await session.scalars(select(ExerciseTemplate).where((ExerciseTemplate.teacher_id == user.id) | ExerciseTemplate.teacher_id.is_(None)).limit(100))).all()
        return {'items': [{'id': row.id, 'kind': row.kind, 'instruction': row.instruction, 'version': row.version, 'active': row.active} for row in rows]}


@router.post('/templates', status_code=201)
async def add_template(body: TemplateInput, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    key = uid()
    async with database(request).transaction() as session:
        session.add(ExerciseTemplate(id=key, teacher_id=user.id, kind=body.kind, instruction=redact_pii(body.instruction)))
        session.add(AuditEvent(actor_id=user.id, action='template_added', target_id=key))
    return {'id': key}


@router.delete('/templates/{template_id}')
async def remove_template(template_id: str, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    async with database(request).transaction() as session:
        row = await session.get(ExerciseTemplate, template_id)
        if not row or row.teacher_id != user.id:
            raise HTTPException(404, 'Template not found.')
        row.active = False
        session.add(AuditEvent(actor_id=user.id, action='template_disabled', target_id=template_id))
    return {'saved': True}


@router.post('/prompts', status_code=201)
async def add_prompt(body: PromptInput, request: Request, user=Depends(staff_user)):
    teacher_only(user)
    key = uid()
    async with database(request).transaction() as session:
        session.add(Prompt(id=key, created_by=user.id, **body.model_dump()))
        session.add(AuditEvent(actor_id=user.id, action='prompt_added', target_id=key))
    return {'id': key}


@router.get('/audit')
async def audit(request: Request, user=Depends(staff_user)):
    teacher_only(user)
    async with database(request).sessions() as session:
        query = select(AuditEvent)
        if user.role != 'admin': query = query.where(AuditEvent.actor_id == user.id)
        rows = (await session.scalars(query.order_by(AuditEvent.created_at.desc()).limit(100))).all()
        return {'items': [{'action': row.action, 'target_id': row.target_id, 'detail': row.detail, 'at': row.created_at} for row in rows]}
