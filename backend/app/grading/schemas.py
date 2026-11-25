import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.grading.aspects import ASPECT_LABELS

MAX_REVIEW_PARAGRAPHS = 12

Band = Annotated[float, Field(ge=0, le=9, multiple_of=0.5)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
CRITERIA = (
    "task_response", "coherence_cohesion", "lexical_resource", "grammatical_range_accuracy",
)
WORDS = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)


def word_count(text: str) -> int:
    return len(WORDS.findall(text))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GradeRequest(StrictModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=3000)]
    essay: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16000)]
    topic: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] = ""


class Scores(StrictModel):
    task_response: Band
    coherence_cohesion: Band
    lexical_resource: Band
    grammatical_range_accuracy: Band


class Evidence(StrictModel):
    quote: Line
    explanation: Line


class Feedback(StrictModel):
    explanation: Line
    strengths: list[Line] = Field(max_length=5)
    weaknesses: list[Line] = Field(max_length=5)
    evidence: list[Evidence] = Field(max_length=4)


class CriterionFeedback(StrictModel):
    task_response: Feedback
    coherence_cohesion: Feedback
    lexical_resource: Feedback
    grammatical_range_accuracy: Feedback


class Correction(StrictModel):
    original: Line
    corrected: Line
    explanation: Line


class ModelGrade(StrictModel):
    criterion_scores: Scores
    criterion_feedback: CriterionFeedback
    grammar_corrections: list[Correction] = Field(max_length=8)
    priority_improvements: list[Line] = Field(min_length=1, max_length=5)


AspectName = Literal[*ASPECT_LABELS]


class AspectReview(StrictModel):
    aspect: AspectName
    score: Band
    explanation: Line


class ParagraphReview(StrictModel):
    paragraph_number: int = Field(ge=1, le=MAX_REVIEW_PARAGRAPHS)
    role: Literal["introduction", "body", "conclusion", "other"]
    summary: Line
    improvement: Line
    evidence: Evidence | None


class LanguageSuggestion(Correction):
    category: Literal["word_choice", "clarity", "style"]


class DetailedModelGrade(ModelGrade):
    aspect_reviews: list[AspectReview] = Field(max_length=len(ASPECT_LABELS))
    paragraph_reviews: list[ParagraphReview] = Field(max_length=MAX_REVIEW_PARAGRAPHS)
    language_suggestions: list[LanguageSuggestion] = Field(max_length=8)


class Attempt(StrictModel):
    status: str
    latency_ms: int
    api_code: int | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class BandConfidence(StrictModel):
    score: float = Field(ge=0.0, le=1.0)
    percentage: int = Field(ge=0, le=100)
    label: Literal["High", "Moderate", "Borderline"]
    band_margin: float = 0.5
    band_range_low: Band
    band_range_high: Band
    note: str


class GradeResult(ModelGrade):
    overall_policy: str = "floor_half_v1"
    fewshot_config: str | None = None
    fewshot_version: str | None = None
    production_fewshot_ready: bool | None = None
    diagnostic_mode: bool = False
    reference_example_ids: list[str] = Field(default_factory=list)
    reference_sha256: str | None = None
    aspect_reviews: list[AspectReview] = Field(default_factory=list)
    paragraph_reviews: list[ParagraphReview] = Field(default_factory=list)
    language_suggestions: list[LanguageSuggestion] = Field(default_factory=list)
    paragraph_count: int | None = None
    task_type: Literal["task_2"] = "task_2"
    estimated_overall_band: Band
    confidence: BandConfidence | None = None
    word_count: int
    model: str
    model_version: str | None = None
    rubric_version: str
    prompt_version: str
    latency_ms: int
    provider_latency_ms: int
    usage: dict[str, int]
    attempts: list[Attempt]
    validation_warnings: list[str]
