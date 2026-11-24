"""Persistent pilot records. Times are UTC epoch seconds, including quota windows."""
import time
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    external_auth_id: Mapped[str] = mapped_column(String(200), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    avatar_url: Mapped[str | None] = mapped_column(String(2000))
    profile_synced_at: Mapped[float | None] = mapped_column(Float)
    reported_full_name: Mapped[str | None] = mapped_column(String(120))
    reported_email: Mapped[str | None] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16), default='student')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    bonus_daily_credits: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    consent_version: Mapped[str | None] = mapped_column(String(80))
    consent_at: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    __table_args__ = (CheckConstraint("role IN ('student','ta','teacher','admin')"),)


class ClassRoom(Base):
    __tablename__ = 'classes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    invite_hash: Mapped[str] = mapped_column(String(64), unique=True)
    join_code: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)
    daily_student_quota: Mapped[int] = mapped_column(Integer, default=3, server_default='3')
    enrollment_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    invite_expires_at: Mapped[float] = mapped_column(Float)
    invite_max_uses: Mapped[int] = mapped_column(Integer, default=45)
    invite_uses: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Membership(Base):
    __tablename__ = 'class_memberships'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    class_id: Mapped[str] = mapped_column(ForeignKey('classes.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(16), default='student')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[float] = mapped_column(Float, default=time.time, server_default='0')
    left_at: Mapped[float | None] = mapped_column(Float)
    removed_at: Mapped[float | None] = mapped_column(Float)

    @property
    def status(self):
        return 'ACTIVE' if self.active else 'LEFT' if self.left_at is not None else 'REMOVED'

    __table_args__ = (UniqueConstraint('class_id', 'user_id'), CheckConstraint("role IN ('student','ta','teacher')"),
        Index('uq_one_active_class_per_student', 'user_id', unique=True,
              postgresql_where=text("role = 'student' AND active"), sqlite_where=text("role = 'student' AND active")))


class Prompt(Base):
    __tablename__ = 'prompts'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    prompt_text: Mapped[str] = mapped_column(Text)
    topic_tag: Mapped[str] = mapped_column(String(100), default='General')
    task_type: Mapped[str] = mapped_column(String(30), default='task_2')
    source: Mapped[str] = mapped_column(String(80), default='original_practice')
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))


class TeacherProfile(Base):
    __tablename__ = 'teacher_profiles'
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    style: Mapped[str] = mapped_column(Text, default='')
    offsets: Mapped[dict] = mapped_column(JSON, default=dict)


class TeacherAnchor(Base):
    __tablename__ = 'teacher_anchors'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    teacher_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExerciseTemplate(Base):
    __tablename__ = 'exercise_templates'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    teacher_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(40))
    instruction: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Submission(Base):
    __tablename__ = 'submissions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    class_id: Mapped[str] = mapped_column(ForeignKey('classes.id'), index=True)
    prompt_id: Mapped[str | None] = mapped_column(ForeignKey('prompts.id'))
    prompt: Mapped[str] = mapped_column(Text)
    essay: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default='QUEUED')
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    credit_reserved_at: Mapped[float | None] = mapped_column(Float)


class SubmissionRequest(Base):
    __tablename__ = 'submission_requests'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reused: Mapped[bool] = mapped_column(Boolean, default=False)


class Assessment(Base):
    __tablename__ = 'assessments'
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    raw_scores: Mapped[dict] = mapped_column(JSON)
    teacher_override: Mapped[dict | None] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))


class PracticeSet(Base):
    __tablename__ = 'practice_sets'
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), primary_key=True)
    state: Mapped[str] = mapped_column(String(24), default='not_generated')
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    templates: Mapped[list] = mapped_column(JSON, default=list)
    draft_answers: Mapped[list] = mapped_column(JSON, default=list)


class PracticeExercise(Base):
    __tablename__ = 'practice_exercises'
    exercise_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey('practice_sets.submission_id', ondelete='CASCADE'), index=True)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    request_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='QUEUED')
    priority: Mapped[int] = mapped_column(Integer, default=10)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[float | None] = mapped_column(Float)
    next_attempt_at: Mapped[float] = mapped_column(Float, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    completed_at: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (UniqueConstraint('user_id', 'kind', 'request_key'),
                      Index('ix_jobs_claim', 'status', 'next_attempt_at', 'priority', 'created_at'))


class QuotaBucket(Base):
    __tablename__ = 'quota_buckets'
    key: Mapped[str] = mapped_column(String(180), primary_key=True)
    events: Mapped[list] = mapped_column(JSON, default=list)


class SystemSetting(Base):
    __tablename__ = 'system_settings'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class ProviderUsage(Base):
    __tablename__ = 'provider_usage'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    model: Mapped[str] = mapped_column(String(120))
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
