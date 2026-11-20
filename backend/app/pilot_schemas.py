from typing import Literal

from pydantic import Field
from app.grading.schemas import GradeRequest, Scores, StrictModel


class SubmitEssay(GradeRequest):
    class_id: str | None = Field(None, max_length=36)
    prompt_id: str | None = Field(None, max_length=80)
    source: None = None
    experiment: Literal['V1_STRATIFIED'] = 'V1_STRATIFIED'


class Consent(StrictModel):
    adult_confirmed: Literal[True]
    accepted_privacy: Literal[True]


class JoinClass(Consent):
    join_code: str = Field(min_length=20, max_length=100)


class CreateClass(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    invite_max_uses: int = Field(45, ge=1, le=100)
    invite_days: int = Field(7, ge=1, le=30)


class AssignMember(StrictModel):
    user_id: str = Field(max_length=36)
    role: Literal['student', 'ta'] = 'student'
    active: bool = True


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
