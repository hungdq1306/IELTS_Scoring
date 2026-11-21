from typing import Literal

from pydantic import Field, field_validator
from app.grading.schemas import GradeRequest, Scores, StrictModel


class SubmitEssay(GradeRequest):
    class_id: str | None = Field(None, max_length=36)
    prompt_id: str | None = Field(None, max_length=80)
    source: None = None
    experiment: Literal['V1_STRATIFIED'] = 'V1_STRATIFIED'


class Consent(StrictModel):
    adult_confirmed: Literal[True]
    accepted_privacy: Literal[True]


class JoinClass(StrictModel):
    join_code: str = Field(min_length=8, max_length=100)
    adult_confirmed: bool = False
    accepted_privacy: bool = False


class CreateClass(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    invite_max_uses: int = Field(45, ge=1, le=100)
    invite_days: int = Field(7, ge=1, le=30)
    daily_student_quota: int | None = Field(None, ge=1, le=100)


class AssignMember(StrictModel):
    user_id: str = Field(max_length=36)
    role: Literal['student', 'ta'] = 'student'
    active: bool = True


class ClassPatch(StrictModel):
    enrollment_open: bool | None = None
    name: str | None = Field(None, min_length=1, max_length=120)
    is_active: bool | None = None
    daily_student_quota: int | None = Field(None, ge=1, le=100)


class ProfileUpdate(StrictModel):
    style: str = Field('', max_length=2000)
    offsets: dict[str, float] = Field(default_factory=dict, max_length=4)


class AnchorInput(GradeRequest):
    scores: Scores


class TemplateInput(StrictModel):
    kind: Literal['multiple_choice', 'sentence_rewriting', 'sentence_correction', 'error_imitation', 'paragraph_revision']
    instruction: str = Field(min_length=10, max_length=2000)


class ScoreOverride(StrictModel):
    scores: Scores
    reason: str = Field(min_length=5, max_length=1500)


class PromptInput(StrictModel):
    prompt_text: str = Field(min_length=10, max_length=3000)
    topic_tag: str = Field(min_length=1, max_length=100)
    is_published: bool = True


class DisplayProfile(StrictModel):
    full_name: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=254)

    @field_validator('full_name', 'email', mode='before')
    @classmethod
    def clean(cls, value, info):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('Expected text.')
        value = value.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Control characters are not allowed.')
        if info.field_name == 'email' and value:
            import re
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                raise ValueError('Invalid email address.')
            value = value.lower()
        return value or None
