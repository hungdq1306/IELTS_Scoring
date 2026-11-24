"""Ordered visual-grounding schema; shape defects are routed by deterministic checks."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

VisualCategory = Literal["chart_time_series", "chart_static", "map", "process", "mixed"]
Confidence = Literal["high", "medium", "low"]


class NumericRow(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    series_name: str
    is_total_row: bool
    values: list[float | None]
    raw_labels: list[str]
    row_confidence: Confidence
    needs_user_check: bool


class NumericTable(BaseModel):
    table_id: str
    panel_title: str
    unit: str
    is_percentage_distribution: bool
    columns: list[str]
    rows: list[NumericRow]


class DiagramElement(BaseModel):
    element_id: str
    zone_or_stage: str
    verbatim_labels: list[str]
    observed_change_or_action: str
    item_confidence: Confidence
    needs_user_check: bool


class Task1ExtractionResult(BaseModel):
    visual_category: VisualCategory
    title_and_units: str
    has_explicit_labels: bool
    image_clarity: Literal["clear", "moderate", "blurry_or_cropped"]
    numeric_tables: list[NumericTable]
    spatial_or_process_steps: list[DiagramElement]
    extraction_notes: str
    key_overview_points: list[str] = Field(min_length=2, max_length=3)
    model_self_confidence: int = Field(ge=0, le=100)


class SanityReport(BaseModel):
    sanity_warnings: list[str] = Field(default_factory=list)
    declared_cells: int = 0
    non_null_cells: int = 0
    table_count: int = 0
    # This checks the declared grid, not completeness against unseen image axes.
    grid_shape_valid: bool = True


class PromptRecord(BaseModel):
    image_hash: str
    image_path: str
    prompt: str
    silver_reference_essay: str
    silver_score: float | None
    essay_count: int
    source_types: list[str] = Field(default_factory=list)
    visual_category_hint: VisualCategory | None = None


class AttemptTelemetry(BaseModel):
    attempt: int
    latency_ms: float
    status: Literal["success", "error"]
    http_code: int | None = None
    error_type: str | None = None
    known_total_tokens: int = 0
    token_usage_available: bool = False
    backoff_ms: float = 0


class BenchmarkRecord(BaseModel):
    image_hash: str
    model: str
    pipeline_version: str
    extraction: Task1ExtractionResult
    sanity_report: SanityReport
    overall_confidence: int
    structural_cap: int
    routing_status: Literal["auto_verified", "needs_user_check"]
    latency_ms: float
    prompt_tokens: int
    candidates_tokens: int
    t_load_ms: float
    t_normalize_ms: float
    t_extract_ms: float
    t_sanity_ms: float
    t_total_ms: float
    attempt_count: int
    total_tokens_including_retries: int
    token_usage_complete: bool
    attempts: list[AttemptTelemetry]
    normalization_reused: bool = True


class AuditResult(BaseModel):
    verdict: Literal["consistent", "minor_variance", "conflict"]
    discrepancy_notes: str


class GoldRecord(BaseModel):
    image_hash: str
    image_path: str
    prompt: str = ""
    visual_category: VisualCategory
    verification_status: Literal["draft", "verified"] = "draft"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    has_explicit_labels: bool | None = None
    numeric_tables: list[NumericTable] = Field(default_factory=list)
    spatial_or_process_steps: list[DiagramElement] = Field(default_factory=list)
    flawed_or_low_confidence: bool | None = None
    review_notes: str = ""
