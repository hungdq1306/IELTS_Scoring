import copy
import hashlib
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.auth import current_user, staff_user
from app.grading.detailed import essay_paragraphs
from app.grading.schemas import CRITERIA
from app.grading.task2 import overall_band
from app.guardrails import fingerprint, redact_pii, validate_input
from app.models import Assessment, AuditEvent, ClassRoom, ExerciseTemplate, Job, Membership, PracticeSet, Prompt, Submission, TeacherAnchor, TeacherProfile, User, uid
from app.pilot_schemas import AnchorInput, AssignMember, Consent, CreateClass, JoinClass, ProfileUpdate, PromptInput, ScoreOverride, SubmitEssay, TemplateInput
from app.practice.schemas import AnswerRequest, PracticeAnswers, PracticeSubmit, RevisionRequest
from app.queue import consume_quota, enqueue, find_request, locked_bucket, ticket
from app.services.drill_gen import public_practice
from app.services.scorer import assignment_safe_config, baseline_config

router = APIRouter(prefix='/api')


def database(request):
    return request.app.state.database


def settings(request):
    return request.app.state.settings


def request_key(value):
    import re
    if not value or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', value):
        raise HTTPException(422, 'A valid Idempotency-Key header is required.')
    return value


async def owned_submission(session, submission_id, user):
    submission = await session.get(Submission, submission_id)
    if not submission or submission.user_id != user.id:
        raise HTTPException(404, 'Submission not found.')
    membership = await session.scalar(select(Membership).where(Membership.class_id == submission.class_id,
                                                              Membership.user_id == user.id, Membership.active.is_(True)))
    classroom = await session.get(ClassRoom, submission.class_id)
    if not membership or not classroom.active:
        raise HTTPException(403, 'Membership is no longer active.')
    return submission


async def class_access(session, class_id, user, manage=False):
    classroom = await session.get(ClassRoom, class_id)
    membership = await session.scalar(select(Membership).where(Membership.class_id == class_id,
                                                               Membership.user_id == user.id, Membership.active.is_(True)))
    if not classroom or not (user.role == 'admin' or classroom.teacher_id == user.id or (not manage and membership and membership.role == 'ta')):
        raise HTTPException(404, 'Class not found.')
    return classroom


@router.get('/auth/config')
async def auth_config(request: Request):
    config = settings(request)
    return {'mode': 'clerk', 'publishable_key': config.clerk_publishable_key, 'issuer': config.clerk_issuer,
            'privacy_version': config.privacy_version, 'adult_only': True,
            'retention_days': config.retention_days, 'gemini_data_policy': config.gemini_data_policy}


@router.get('/auth/me')
async def me(request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        memberships = (await session.execute(select(Membership, ClassRoom).join(ClassRoom, ClassRoom.id == Membership.class_id)
            .where(Membership.user_id == user.id, Membership.active.is_(True), ClassRoom.active.is_(True)))).all()
    return {'id': user.id, 'role': user.role, 'consent_version': user.consent_version,
            'classes': [{'id': classroom.id, 'name': classroom.name, 'role': membership.role} for membership, classroom in memberships]}


@router.post('/auth/consent')
async def consent(body: Consent, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        stored = await session.get(User, user.id)
        stored.consent_version, stored.consent_at = settings(request).privacy_version, time.time()
    return {'accepted': True}


@router.post('/classes/join')
async def join(body: JoinClass, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        await consume_quota(session, 'join:' + user.id, 10, 3600)
        classroom = await session.scalar(select(ClassRoom).where(ClassRoom.invite_hash == hashlib.sha256(body.join_code.encode()).hexdigest()).with_for_update())
        if not classroom or not classroom.active or classroom.invite_expires_at < time.time():
            # Return after commit so failed guesses still consume the brute-force budget.
            invalid = True
        else:
            invalid = False
            membership = await session.scalar(select(Membership).where(Membership.class_id == classroom.id, Membership.user_id == user.id))
            if not membership:
                if classroom.invite_uses >= classroom.invite_max_uses:
                    invalid = True
                else:
                    classroom.invite_uses += 1
                    session.add(Membership(class_id=classroom.id, user_id=user.id))
            elif not membership.active:
                invalid = True  # A revoked student cannot rejoin with an old class code.
            if not invalid:
                stored = await session.get(User, user.id)
                stored.consent_version, stored.consent_at = settings(request).privacy_version, time.time()
                result = {'id': classroom.id, 'name': classroom.name}
    if invalid:
        raise HTTPException(400, 'Mã mời không hợp lệ, đã hết hạn hoặc không còn chỗ.')
    return result


@router.get('/prompts')
async def prompts(request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        rows = (await session.scalars(select(Prompt).where(Prompt.is_published.is_(True)).order_by(Prompt.id).limit(100))).all()
    return {'items': [{'id': row.id, 'prompt_text': row.prompt_text, 'topic_tag': row.topic_tag, 'source': row.source} for row in rows]}


@router.post('/submissions', status_code=202)
@router.post('/writing/task2/evaluate', status_code=202)
async def submit(body: SubmitEssay, request: Request, idempotency_key: str | None = Header(None), user=Depends(current_user)):
    key = request_key(idempotency_key)
    config = settings(request)
    if user.consent_version != config.privacy_version:
        raise HTTPException(403, 'Please accept the adult-only pilot and privacy notice before submitting.')
    payload = body.model_dump()
    async with database(request).transaction() as session:
        await locked_bucket(session, 'submit:' + user.id)
        prior = await find_request(session, user.id, 'score', key, payload)
        if prior:
            return ticket(prior)
        memberships = list((await session.scalars(select(Membership).join(ClassRoom, ClassRoom.id == Membership.class_id)
            .where(Membership.user_id == user.id, Membership.active.is_(True), ClassRoom.active.is_(True)))).all())
        membership = next((member for member in memberships if member.class_id == body.class_id), None) if body.class_id else memberships[0] if len(memberships) == 1 else None
        if not membership:
            raise HTTPException(403, 'Join a class first, or select a class if you belong to several.')
        classroom = await session.get(ClassRoom, membership.class_id)
        prompt = body.prompt
        if body.prompt_id:
            entry = await session.get(Prompt, body.prompt_id)
            if not entry or not entry.is_published:
                raise HTTPException(404, 'Prompt not found.')
            prompt = entry.prompt_text
        count, warnings = validate_input(prompt, body.essay)
        await consume_quota(session, 'submission:' + user.id, config.daily_submission_limit)
        profile = await session.get(TeacherProfile, classroom.teacher_id)
        fewshot = copy.deepcopy(baseline_config())
        anchors = list((await session.scalars(select(TeacherAnchor).where(TeacherAnchor.teacher_id == classroom.teacher_id, TeacherAnchor.active.is_(True)).order_by(TeacherAnchor.id).limit(8))).all())
        if anchors:
            fewshot['examples'] = [anchor.payload for anchor in anchors]
            fewshot['reference_sha256'] = fingerprint(fewshot['examples'])
            fewshot['_protected_references'] = [{'essay': anchor.payload['student_essay'], 'question': anchor.payload['question']} for anchor in anchors]
            fewshot['version'] = 'teacher-' + fewshot['reference_sha256'][:12]
        fewshot = assignment_safe_config(fewshot, prompt)
        snapshot = {'fewshot': fewshot, 'style': profile.style if profile else '', 'offsets': profile.offsets if profile else {},
                    'version': profile.version if profile else 0}
        submission = Submission(user_id=user.id, class_id=classroom.id, prompt_id=body.prompt_id,
                                prompt=prompt, essay=body.essay, word_count=count, warnings=warnings, config_snapshot=snapshot)
        session.add(submission)
        await session.flush()
        job = await enqueue(session, config, user.id, submission.id, 'score', key, payload)
        return ticket(job)


@router.get('/jobs/{job_id}')
async def job_status(job_id: str, request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        job = await session.get(Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, 'Job not found.')
        await owned_submission(session, job.submission_id, user)
        ahead = await session.scalar(select(func.count()).select_from(Job).where(Job.status == 'QUEUED',
            (Job.priority < job.priority) | ((Job.priority == job.priority) & (Job.created_at < job.created_at)))) if job.status == 'QUEUED' else 0
        result = job.result
        if job.kind == 'score' and job.status == 'COMPLETED':
            assessment = await session.get(Assessment, job.submission_id)
            result = {**effective_grade(assessment), 'submission_id': job.submission_id}
        return {**ticket(job), 'queue_position': ahead + 1 if job.status == 'QUEUED' else None,
                'attempt_count': job.attempt_count, 'retry_at': job.next_attempt_at, 'error_code': job.error_code,
                'result': result if job.status == 'COMPLETED' else None}


@router.get('/submissions/{submission_id}')
@router.get('/writing/task2/{submission_id}/submission')
async def get_submission(submission_id: str, request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        submission = await owned_submission(session, submission_id, user)
        assessment = await session.get(Assessment, submission_id)
        return {'submission_id': submission.id, 'class_id': submission.class_id, 'prompt': submission.prompt,
                'essay': submission.essay, 'status': submission.status,
                'grade': effective_grade(assessment) if assessment else None}


@router.get('/submissions/{submission_id}/result')
async def submission_result(submission_id: str, request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        await owned_submission(session, submission_id, user)
        job = await session.scalar(select(Job).where(Job.submission_id == submission_id, Job.kind == 'score'))
        if not job:
            raise HTTPException(404, 'Assessment job not found.')
        return JSONResponse(ticket(job), status_code=202)


def effective_grade(assessment):
    result = {**assessment.result, 'teacher_reviewed': bool(assessment.teacher_override)}
    if assessment.teacher_override:
        result.update(criterion_scores=assessment.teacher_override['scores'], estimated_overall_band=assessment.teacher_override['overall'])
    return result


@router.get('/submissions')
@router.get('/practice/submissions')
async def history(request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        rows = (await session.scalars(select(Submission).join(Membership, (Membership.class_id == Submission.class_id) & (Membership.user_id == Submission.user_id))
            .join(ClassRoom, ClassRoom.id == Submission.class_id)
            .where(Submission.user_id == user.id, Membership.active.is_(True), ClassRoom.active.is_(True))
            .order_by(Submission.created_at.desc(), Submission.id).limit(100))).all()
        return {'items': [{'submission_id': row.id, 'prompt': row.prompt, 'created': row.created_at, 'status': row.status} for row in rows]}


async def practice_context(session, submission_id, user):
    submission = await owned_submission(session, submission_id, user)
    practice = await session.get(PracticeSet, submission_id)
    return submission, practice


@router.get('/writing/task2/{submission_id}/exercises')
async def get_practice(submission_id: str, request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        _, practice = await practice_context(session, submission_id, user)
        jobs = (await session.scalars(select(Job).where(Job.submission_id == submission_id))).all()
        return public_practice(submission_id, practice.state if practice else 'not_generated', practice.payload if practice else {}, jobs)


@router.post('/writing/task2/{submission_id}/exercises')
async def make_practice(submission_id: str, request: Request, user=Depends(current_user)):
    config = settings(request)
    if not config.enable_practice_gen:
        raise HTTPException(409, 'Practice generation is currently disabled.')
    async with database(request).transaction() as session:
        await locked_bucket(session, 'practice:' + user.id)
        submission, practice = await practice_context(session, submission_id, user)
        if submission.status != 'COMPLETED':
            raise HTTPException(409, 'Wait for your assessment first.')
        if practice and practice.state == 'ready':
            return public_practice(submission_id, practice.state, practice.payload)
        existing = list((await session.scalars(select(Job).where(Job.submission_id == submission_id, Job.kind == 'practice').order_by(Job.created_at.desc()))).all())
        if existing and existing[0].status in ('QUEUED', 'RUNNING'):
            return JSONResponse(ticket(existing[0]), status_code=202)
        if len(existing) >= 2:
            raise HTTPException(429, 'Practice generation limit reached for this essay.')
        await consume_quota(session, 'practice-calls:' + user.id, config.daily_practice_limit)
        classroom = await session.get(ClassRoom, submission.class_id)
        templates = list((await session.scalars(select(ExerciseTemplate).where(ExerciseTemplate.active.is_(True),
                            (ExerciseTemplate.teacher_id == classroom.teacher_id) | ExerciseTemplate.teacher_id.is_(None)).order_by(ExerciseTemplate.id).limit(12))).all())
        if not practice:
            practice = PracticeSet(submission_id=submission_id)
            session.add(practice)
        practice.state = 'generating'
        practice.templates = [{'id': row.id, 'version': row.version, 'kind': row.kind, 'instruction': redact_pii(row.instruction)} for row in templates]
        job = await enqueue(session, config, user.id, submission_id, 'practice', submission_id + '-' + str(len(existing)), {})
        return JSONResponse(ticket(job), status_code=202)


async def exercise_context(session, exercise_id, user):
    # Exercise IDs are random, but authorization still checks the parent submission.
    practices = (await session.execute(select(PracticeSet, Submission).join(Submission, Submission.id == PracticeSet.submission_id)
                                       .where(Submission.user_id == user.id, PracticeSet.state == 'ready').limit(100))).all()
    for practice, submission in practices:
        exercise = next((item for item in practice.payload.get('exercises', []) if item['exercise_id'] == exercise_id), None)
        if exercise:
            await owned_submission(session, submission.id, user)
            return submission, practice, exercise
    raise HTTPException(404, 'Exercise not found.')


async def queue_operation(session, config, user, submission_id, kind, key, payload, maximum):
    await locked_bucket(session, 'practice:' + user.id)
    prior = await find_request(session, user.id, kind, key, payload)
    if prior:
        return JSONResponse(ticket(prior), status_code=202)
    count = await session.scalar(select(func.count()).select_from(Job).where(Job.submission_id == submission_id, Job.kind == kind))
    if count >= maximum:
        raise HTTPException(429, 'Practice attempt limit reached for this essay.')
    await consume_quota(session, 'practice-calls:' + user.id, config.daily_practice_limit)
    job = await enqueue(session, config, user.id, submission_id, kind, key, payload)
    return JSONResponse(ticket(job), status_code=202)


@router.post('/exercises/{exercise_id}/answer')
async def answer(exercise_id: str, body: AnswerRequest, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        submission, _, _ = await exercise_context(session, exercise_id, user)
        return await queue_operation(session, settings(request), user, submission.id, 'answer', body.request_id,
                                     {'exercise_id': exercise_id, 'answer': body.answer}, 20)


@router.get('/exercises/{exercise_id}/feedback')
async def feedback(exercise_id: str, request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        submission, _, _ = await exercise_context(session, exercise_id, user)
        jobs = (await session.scalars(select(Job).where(Job.submission_id == submission.id, Job.status == 'COMPLETED', Job.kind.in_(['answer', 'practice_batch']))
                                      .order_by(Job.completed_at.desc()))).all()
        for job in jobs:
            for result in job.result.get('items', []) if job.kind == 'practice_batch' else [job.result]:
                if result['exercise_id'] == exercise_id:
                    return result
        raise HTTPException(404, 'No saved feedback yet.')


@router.post('/exercises/{exercise_id}/hint')
async def hint(exercise_id: str, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        submission, _, exercise = await exercise_context(session, exercise_id, user)
        await locked_bucket(session, 'hint:' + user.id)
        row = await find_request(session, user.id, 'hint', exercise_id, {})
        if not row:
            session.add(Job(user_id=user.id, submission_id=submission.id, kind='hint', request_key=exercise_id,
                            fingerprint=fingerprint({}), status='COMPLETED', result={}, completed_at=time.time()))
        return {'hint': exercise['hint'], 'exercise_id': exercise_id, 'human_reviewed': False}


@router.post('/writing/task2/{submission_id}/revision')
async def revise(submission_id: str, body: RevisionRequest, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        submission, practice = await practice_context(session, submission_id, user)
        paragraphs = essay_paragraphs(submission.essay)
        if body.paragraph_number > len(paragraphs) or not practice:
            raise HTTPException(422, 'Choose a paragraph with an approved weakness.')
        errors = [error for error in practice.payload.get('errors', []) if error['paragraph_number'] == body.paragraph_number and error['exercise_eligible']]
        if not errors:
            raise HTTPException(422, 'This paragraph has no approved weakness.')
        return await queue_operation(session, settings(request), user, submission_id, 'revision', body.request_id,
            {'paragraph_number': body.paragraph_number, 'before': paragraphs[body.paragraph_number - 1], 'after': body.answer,
             'weaknesses': errors, 'question': submission.prompt}, 5)


@router.get('/writing/task2/{submission_id}/practice-attempt')
async def practice_attempt(submission_id: str, request: Request, user=Depends(current_user)):
    async with database(request).sessions() as session:
        _, practice = await practice_context(session, submission_id, user)
        last = await session.scalar(select(Job).where(Job.submission_id == submission_id, Job.kind == 'practice_batch').order_by(Job.created_at.desc()).limit(1))
        return {'submission_id': submission_id, 'answers': practice.draft_answers if practice else [],
                'state': 'complete' if last and last.status == 'COMPLETED' else 'pending' if last and last.status in ('QUEUED', 'RUNNING') else 'failed' if last else 'draft',
                'result': last.result if last and last.status == 'COMPLETED' else None,
                'exercises_total': len(practice.payload.get('exercises', [])) if practice else 0,
                'evaluation_model': request.app.state.answer_provider.settings.model}


async def validate_answers(session, submission_id, user, answers, complete=False):
    _, practice = await practice_context(session, submission_id, user)
    if not practice or practice.state != 'ready' or not practice.payload.get('exercises'):
        raise HTTPException(409, 'Generate practice before answering.')
    expected = {exercise['exercise_id'] for exercise in practice.payload['exercises']}
    supplied = [answer.exercise_id for answer in answers]
    if len(set(supplied)) != len(supplied) or not set(supplied) <= expected or (complete and (set(supplied) != expected or any(not answer.answer.strip() for answer in answers))):
        raise HTTPException(422, 'Answers must contain the correct exercise IDs; complete every exercise before submitting.')
    return practice, sorted([answer.model_dump() for answer in answers], key=lambda row: row['exercise_id'])


@router.put('/writing/task2/{submission_id}/practice-attempt')
async def save_attempt(submission_id: str, body: PracticeAnswers, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        await locked_bucket(session, 'practice:' + user.id)
        practice, answers = await validate_answers(session, submission_id, user, body.answers)
        practice.draft_answers = answers
        return {'state': 'saved', 'answers': answers, 'submission_id': submission_id}


@router.post('/writing/task2/{submission_id}/practice-attempt/submit')
async def submit_attempt(submission_id: str, body: PracticeSubmit, request: Request, user=Depends(current_user)):
    async with database(request).transaction() as session:
        practice, answers = await validate_answers(session, submission_id, user, body.answers, complete=True)
        practice.draft_answers = answers
        return await queue_operation(session, settings(request), user, submission_id, 'practice_batch', body.request_id, {'answers': answers}, 3)


@router.get('/writing/task2/{submission_id}/progress')
async def progress(submission_id: str, request: Request, user=Depends(current_user)):
    from collections import Counter
    async with database(request).sessions() as session:
        _, practice = await practice_context(session, submission_id, user)
        jobs = list((await session.scalars(select(Job).where(Job.submission_id == submission_id, Job.status == 'COMPLETED')
                                          .order_by(Job.completed_at, Job.id))).all())
    payload = practice.payload if practice else {}
    exercises, errors = payload.get('exercises', []), payload.get('errors', [])
    records = []
    for job in jobs:
        if job.kind == 'answer': records.append(job.result)
        elif job.kind == 'practice_batch': records.extend(job.result['items'])
    first = {}
    for row in records: first.setdefault(row['exercise_id'], row)
    hints = {job.request_key for job in jobs if job.kind == 'hint'}
    done = {row['exercise_id'] for row in records if row['outcome'] == 'correct'}
    unassisted = [row for key, row in first.items() if key not in hints]
    return {'submission_id': submission_id, 'exercises_total': len(exercises), 'exercises_completed': len(done),
            'attempts': len(records), 'first_attempt_accuracy': sum(row['outcome'] == 'correct' for row in first.values()) / len(first) if first else None,
            'unassisted_first_attempt_accuracy': sum(row['outcome'] == 'correct' for row in unassisted) / len(unassisted) if unassisted else None,
            'hints_used': len(hints), 'skills_practiced': sorted({exercise['skill'] for exercise in exercises if exercise['exercise_id'] in first}),
            'common_error_categories': dict(Counter(error['category'] for error in errors if error['exercise_eligible'])),
            'repeated_error_patterns': dict(Counter(error['subtype'] for error in errors if error['exercise_eligible'])),
            'skills_requiring_practice': sorted({exercise['skill'] for exercise in exercises if exercise['exercise_id'] not in done}),
            'errors_successfully_corrected': len({exercise['source_error_id'] for exercise in exercises if exercise['exercise_id'] in done}),
            'revisions': [job.result for job in jobs if job.kind == 'revision'], 'caveat': 'Automated practice outcomes, not verified proficiency gains.'}
