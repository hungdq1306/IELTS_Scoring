from typing import Literal

from app.grading.schemas import Attempt, GradeRequest, GradeResult, StrictModel

Split = Literal["smoke", "dev", "test_locked", "lexibot"]


class Health(StrictModel):
    status: Literal["ok"] = "ok"
    model_configured: bool
    model: str


class Models(StrictModel):
    configured_model: str
    key_configured: bool
    free_tier_candidates: list[str]
    available_to_key: list[str] | None = None


class ErrorBody(StrictModel):
    code: str
    message: str
    retry_after: float | None = None


class ErrorResponse(StrictModel):
    detail: ErrorBody


class SourceSelection(StrictModel):
    split: Split
    essay_id: str


class EvaluateRequest(GradeRequest):
    experiment: Literal["A1", "FS0", "FS1", "FS2", "FS5", "FS5_FULL", "FS5_COMPACT", "FS7", "V1_STRATIFIED"] = "A1"
    source: SourceSelection | None = None


class Evaluation(GradeResult):
    submission_id: str | None = None
    saved_run_id: str | None = None


class SplitInfo(StrictModel):
    name: str
    count: int
    bands: list[float]
    source: str = "Writing9"
    label_provenance: str = ""


class DatasetInfo(StrictModel):
    name: str
    revision: str | None = None
    label_provenance: str
    splits: list[SplitInfo]


class EssayOverview(StrictModel):
    essay_id: str
    prompt: str
    topic: str
    word_count: int
    gold_overall: float


class Essay(EssayOverview):
    essay: str
    gold_tr: float
    gold_cc: float
    gold_lr: float
    gold_gra: float
    source_dataset: str
    prompt_group: str
    quality_flags: str


class EssayPage(StrictModel):
    total: int
    items: list[EssayOverview]


class RunMetadata(StrictModel):
    fewshot: dict | None = None
    run_id: str
    kind: Literal["benchmark", "manual"]
    selected_essay_id: str | None = None
    provider: str
    dataset: str
    dataset_revision: str | None
    label_provenance: str
    split: str
    expected: int
    model: str
    dataset_sha256: str
    experiment: str
    prompt_version: str
    rubric_version: str
    prompt_sha256: str
    created_at: str
    parameters: dict[str, int]


class ScoresSummary(StrictModel):
    n: int
    mae: float | None
    rmse: float | None
    qwk: float | None
    exact: float | None
    within_05: float | None
    within_10: float | None
    bias: float | None
    median_absolute_error: float | None = None


class OperationalLatency(StrictModel):
    mean: float | None
    median: float | None
    p90: float | None
    p95: float | None


class RunSummary(StrictModel):
    expected: int
    attempted: int
    completed: int
    failed: int
    unattempted: int
    excluded: int
    overall: ScoresSummary
    ci95: dict[str, list[float]]
    criteria: dict[str, ScoresSummary]
    by_band: dict[str, ScoresSummary]
    by_length: dict[str, ScoresSummary]
    by_topic: dict[str, ScoresSummary]
    confusion: dict[str, dict[str, int]]
    error_histogram: dict[str, int]
    latency_ms: OperationalLatency
    provider_attempts: int
    successful_api_calls: int
    failed_api_calls: int
    rate_limit_errors: int
    invalid_json: int
    invalid_schema: int
    usage: dict[str, int]
    attempt_status: dict[str, int]
    episode_status: dict[str, int]


class RunInfo(StrictModel):
    run: RunMetadata
    summary: RunSummary
    status: Literal["complete", "in_progress", "incomplete"]


class ReferenceScores(StrictModel):
    overall: float
    tr: float
    cc: float
    lr: float
    gra: float


class RunResult(StrictModel):
    essay_id: str
    prompt: str
    essay: str
    gold: ReferenceScores
    topic: str
    word_count: int
    quality_flags: str
    timestamp: str
    prediction: GradeResult | None
    attempts: list[Attempt]
    error: str | None
    status: str
