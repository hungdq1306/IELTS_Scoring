"""Enrollment, quota continuity and unverified profile policy regressions."""
import asyncio
import time
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Base, User, ClassRoom, Membership, AuditEvent
from app.pilot_schemas import DisplayProfile
from app.identity import public_profile
from test_concurrency_and_guardrails import application, headers, submit, RESULT


def test_partial_unique_index_and_staff_exemption():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        student = User(external_auth_id='student')
        teacher = User(external_auth_id='teacher', role='teacher')
        db.add_all([student, teacher]); db.flush()
        rooms = [ClassRoom(name=n, teacher_id=teacher.id, invite_hash=n, invite_expires_at=9999999999) for n in ['A','B']]
        db.add_all(rooms); db.flush()
        db.add(Membership(user_id=student.id,class_id=rooms[0].id)); db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(Membership(user_id=student.id,class_id=rooms[1].id)); db.flush()
        for room in rooms:
            db.add(Membership(user_id=teacher.id,class_id=room.id,role='teacher'))
        db.flush()
        first=db.scalar(select(Membership).where(Membership.user_id==student.id))
        first.active=False; first.left_at=time.time();db.flush()
        db.add(Membership(user_id=student.id,class_id=rooms[1].id));db.flush()
        assert first.status=='LEFT'
    engine.dispose()


def test_profile_unicode_validation_and_provenance():
    assert DisplayProfile(full_name='  Hưng Đặng  ',email=' HUNG@Example.com ').model_dump()=={'full_name':'Hưng Đặng','email':'hung@example.com'}
    from pydantic import ValidationError
    for values in [dict(email='bad'),dict(full_name='x'*121),dict(email='x'*255),dict(full_name='a\nb'),dict(role='admin'),dict(credits=20),dict(is_active=True),dict(user_id='other')]:
        with pytest.raises(ValidationError):DisplayProfile(**values)
    u=User(id='u',external_auth_id='clerk',reported_full_name='Quang Hưng Đặng',reported_email='hung@example.com')
    assert public_profile(u)['name_source']=='self_reported'
    u.full_name='Verified Name';u.email='verified@example.com'
    assert public_profile(u)['full_name']=='Verified Name' and public_profile(u)['email_source']=='provider'


def test_leave_join_quota_continuity_and_original_job(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            staff=headers(subject='user_teacher')
            target=(await c.client.post('/api/teacher/classes',headers=staff,json={'name':'Next'})).json()
            denied=await c.client.post('/api/classes/join',headers=headers(),json={'join_code':target['join_code']})
            assert denied.status_code==409 and denied.json()['detail']['code']=='ALREADY_IN_CLASS'
            admitted=await submit(c);sid=admitted.json()['submission_id'];jid=admitted.json()['job_id']
            left=await c.client.post(f'/api/classes/{c.room.id}/leave',headers=headers())
            assert left.status_code==200 and left.json()['status']=='LEFT'
            assert (await submit(c,key='after_leave_01')).status_code==403
            history=(await c.client.get('/api/practice/submissions',headers=headers())).json()['items']
            assert any(row['submission_id']==sid for row in history)
            assert (await c.client.get('/api/jobs/'+jid,headers=headers())).status_code==200
            from app.queue import claim
            from app.worker import Worker
            from test_concurrency_and_guardrails import FakeProvider
            job=await claim(c.database,c.settings)
            assert await Worker(c.database,c.settings,FakeProvider(),FakeProvider()).finish(job,result=RESULT)
            saved=(await c.client.get('/api/submissions/'+sid,headers=headers())).json()
            assert saved['class_id']==c.room.id and saved['status']=='COMPLETED'
            cooldown=await c.client.post('/api/classes/join',headers=headers(),json={'join_code':target['join_code']})
            assert cooldown.status_code==429 and cooldown.json()['detail']['code']=='CLASS_SWITCH_COOLDOWN'
            async with c.database.transaction() as db:
                await db.execute(update(Membership).where(Membership.user_id==c.accounts[0].id,Membership.class_id==c.room.id).values(left_at=time.time()-86401))
            joined=await c.client.post('/api/classes/join',headers=headers(),json={'join_code':target['join_code']})
            assert joined.status_code==200 and joined.json()['quota_status']['used_today']==1
            assert joined.json()['quota_status']['remaining_today']==2
            assert (await c.client.delete(f"/api/teacher/classes/{target['id']}/students/{c.accounts[0].id}",headers=staff)).status_code==200
            removed=await c.client.post('/api/classes/join',headers=headers(),json={'join_code':target['join_code']})
            assert removed.status_code==403 and removed.json()['detail']['code']=='REMOVED_FROM_CLASS'
    asyncio.run(scenario())


def test_join_race_enrollment_lock_and_audit(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            staff=headers(subject='user_teacher')
            rooms=[(await c.client.post('/api/teacher/classes',headers=staff,json={'name':name})).json() for name in ['A','B']]
            async with c.database.transaction() as db:
                await db.execute(update(Membership).where(Membership.user_id==c.accounts[0].id).values(active=False,left_at=time.time()-86401))
            a=rooms[0]
            assert (await c.client.patch('/api/teacher/classes/'+a['id'],headers=staff,json={'enrollment_open':False})).status_code==200
            locked=await c.client.post('/api/classes/join',headers=headers(),json={'join_code':a['join_code']})
            assert locked.status_code==403 and locked.json()['detail']['code']=='CLASS_ENROLLMENT_LOCKED'
            await c.client.patch('/api/teacher/classes/'+a['id'],headers=staff,json={'enrollment_open':True})
            res=await asyncio.gather(*(c.client.post('/api/classes/join',headers=headers(),json={'join_code':r['join_code']}) for r in rooms))
            assert sorted(r.status_code for r in res)==[200,409]
            async with c.database.sessions() as db:
                actions=list((await db.scalars(select(AuditEvent.action))).all())
                assert 'student_joined_class' in actions and 'class_enrollment_toggled' in actions
    asyncio.run(scenario())


def test_own_display_profile_cannot_change_authority(tmp_path):
    async def scenario():
        async with application(tmp_path) as c:
            changed=await c.client.patch('/api/auth/me',headers=headers(),json={'full_name':'Quang Hưng Đặng','email':' HUNG@Example.com '})
            assert changed.status_code==200 and changed.json()['full_name']=='Quang Hưng Đặng'
            assert changed.json()['email_source']=='self_reported'
            assert (await c.client.patch('/api/auth/me',headers=headers(),json={'role':'admin'})).status_code==422
            async with c.database.transaction() as db:
                u=await db.get(User,c.accounts[0].id);u.full_name='JWT Name';u.email='jwt@example.com'
            protected=(await c.client.patch('/api/auth/me',headers=headers(),json={'full_name':'Fake','email':'fake@example.com'})).json()
            assert protected['full_name']=='JWT Name' and protected['email']=='jwt@example.com'
            assert (await c.client.get('/api/auth/me',headers=headers())).json()['role']=='student'
    asyncio.run(scenario())
