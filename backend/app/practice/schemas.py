from typing import Literal
from pydantic import Field, model_validator, field_validator
from app.grading.schemas import StrictModel, Line

TAXONOMY={
 "grammar": ["subject_verb_agreement","verb_tense","articles","prepositions","sentence_structure","sentence_fragments","run_on_sentences","word_forms","grammatical_range","punctuation"],
 "vocabulary": ["word_choice","collocation","repetition","unnatural_phrasing","register","word_formation"],
 "coherence": ["paragraph_progression","linking_devices","unclear_reference","logical_gaps","paragraph_structure"],
 "task_response": ["underdeveloped_ideas","unsupported_claims","irrelevant_examples","missing_explanation","incomplete_response","unclear_position"]}
CRITERION={"grammar":"GRA","vocabulary":"LR","coherence":"CC","task_response":"TR"}
ExerciseType=Literal["multiple_choice","error_identification","sentence_correction","sentence_rewriting","paragraph_revision","error_imitation"]

class ErrorDraft(StrictModel):
 error_id: str = Field(min_length=1,max_length=80)
 criterion: Literal["GRA","LR","CC","TR"]
 category: Literal["grammar","vocabulary","coherence","task_response"]
 subtype: str = Field(min_length=1,max_length=80)
 original_quote: Line
 suggested_correction: str = Field(max_length=3000)
 explanation: Line
 severity: Literal["low","medium","high"]
 paragraph_number: int = Field(ge=1,le=100)
 optional_style: bool

class ExerciseDraft(StrictModel):
 source_error_id: str = Field(min_length=1,max_length=80)
 type: ExerciseType
 skill: str = Field(min_length=1,max_length=80)
 difficulty: int = Field(ge=1,le=4)
 instruction: Line
 question: str = Field(min_length=3,max_length=3500)
 options: list[Line] = Field(max_length=4)
 correct_answer: str = Field(min_length=1,max_length=3500)
 accepted_alternatives: list[Line] = Field(max_length=5)
 target_span: str = Field(max_length=500)
 explanation: Line
 hint: Line
 learning_objective: Line
 evaluation_rubric: list[Line] = Field(min_length=1,max_length=5)

class PracticeDraft(StrictModel):
 errors: list[ErrorDraft] = Field(max_length=10)
 exercises: list[ExerciseDraft] = Field(max_length=5)

class ErrorJudgment(StrictModel):
 error_id: str
 real_error: bool
 correction_valid: bool
 reason: Line

class ExerciseJudgment(StrictModel):
 index: int = Field(ge=0,le=4)
 aligned: bool
 answer_correct: bool
 unambiguous: bool
 explanation_correct: bool
 difficulty_appropriate: bool
 distractors_plausible: bool
 no_answer_leak: bool
 no_injection: bool
 reason: Line

class PracticeReview(StrictModel):
 errors: list[ErrorJudgment] = Field(max_length=10)
 exercises: list[ExerciseJudgment] = Field(max_length=5)

class AnswerRequest(StrictModel):
 answer: str = Field(min_length=1,max_length=5000)
 request_id: str = Field(min_length=8,max_length=80,pattern=r"^[A-Za-z0-9_-]+$")

 @field_validator('answer')
 @classmethod
 def nonblank_answer(cls,value):
  if not value.strip():raise ValueError('Answer must contain text.')
  return value

class AnswerAssessment(StrictModel):
 outcome: Literal["correct","incorrect","partially_correct"]
 explanation: Line
 suggested_improvement: str = Field(max_length=3500)
 target_fixed: bool
 meaning_preserved: bool
 no_new_serious_errors: bool

class RevisionRequest(AnswerRequest):
 paragraph_number: int = Field(ge=1,le=100)

class PublicError(StrictModel):
 error_id: str
 criterion: str
 category: str
 subtype: str
 original_quote: str
 paragraph_number: int
 start: int
 end: int
 severity: str
 explanation: str
 evidence_verified: bool
 exercise_eligible: bool
 semantic_status: str
 recurrence: int

class PublicExercise(StrictModel):
 exercise_id: str
 source_error_id: str
 type: ExerciseType
 skill: str
 difficulty: int
 instruction: str
 question: str
 options: list[str]
 learning_objective: str
 validation_status: str
 completed: bool = False
 attempts: int = 0
 hint_used: bool = False

class PracticeResponse(StrictModel):
 submission_id: str
 state: str
 errors: list[PublicError]
 exercises: list[PublicExercise]
 exclusions: list[dict]
 message: str

class AnswerResponse(StrictModel):
 attempt_id: str
 exercise_id: str
 outcome: Literal["correct","incorrect","partially_correct"]
 explanation: str
 suggested_improvement: str
 target_fixed: bool
 meaning_preserved: bool
 no_new_serious_errors: bool
 evaluator: str
 human_reviewed: bool = False
 correct_answer: str
 accepted_alternatives: list[str]
 attempt_number: int
 hint_used: bool

class ProgressResponse(StrictModel):
 submission_id: str
 exercises_total: int
 exercises_completed: int
 attempts: int
 first_attempt_accuracy: float | None
 unassisted_first_attempt_accuracy: float | None
 hints_used: int
 skills_practiced: list[str]
 common_error_categories: dict[str,int]
 repeated_error_patterns: dict[str,int]
 skills_requiring_practice: list[str]
 errors_successfully_corrected: int
 revisions: list[dict]
 caveat: str
