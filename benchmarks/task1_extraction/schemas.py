from typing import Literal
from pydantic import BaseModel, Field


class StructuredFact(BaseModel):
    fact_id: str
    subject_or_stage: str
    extracted_value_or_state: str
    item_confidence: Literal['high', 'medium', 'low']
    needs_user_check: bool


class Task1ExtractionResult(BaseModel):
    visual_category: Literal['chart_time_series', 'chart_static', 'map', 'process', 'mixed']
    title_and_units: str
    has_explicit_labels: bool
    image_clarity: Literal['clear', 'moderate', 'blurry_or_cropped']
    extraction_notes: str
    structured_facts: list[StructuredFact] = Field(min_length=1)
    key_overview_points: list[str] = Field(min_length=2, max_length=3)
    model_self_confidence: int = Field(ge=0, le=100)


class PromptRecord(BaseModel):
    image_hash: str
    image_path: str
    prompt: str
    silver_reference_essay: str
    silver_score: float | None
    essay_count: int


class BenchmarkRecord(BaseModel):
    image_hash: str
    model: str
    pipeline_version: str
    extraction: Task1ExtractionResult
    overall_confidence: int
    structural_cap: int
    routing_status: Literal['auto_verified', 'needs_user_check']
    latency_ms: float
    prompt_tokens: int
    candidates_tokens: int


class AuditResult(BaseModel):
    verdict: Literal['consistent', 'minor_variance', 'conflict']
    discrepancy_notes: str
