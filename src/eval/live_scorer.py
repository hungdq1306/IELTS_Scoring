"""Live Gemini Few-Shot IELTS Writing Task 2 scorer with rationale, latency, and token logging."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.data.tiering import EssayRecord, compute_ielts_overall, round_half

# Ensure backend package is importable when running from repo root
_BACKEND_DIR = str(Path(__file__).resolve().parents[2] / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.config import load_settings  # noqa: E402
from app.grading.rubric import SYSTEM_PROMPT  # noqa: E402
from app.providers.gemini import GeminiProvider  # noqa: E402
from src.eval.prompt_v1 import SYSTEM_PROMPT_V1, build_user_prompt_v1  # noqa: E402


class CriterionRationale(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_response: str = Field(..., min_length=1)
    coherence_cohesion: str = Field(..., min_length=1)
    lexical_resource: str = Field(..., min_length=1)
    grammatical_range_accuracy: str = Field(..., min_length=1)


class CriterionScorePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_response: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)
    coherence_cohesion: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)
    lexical_resource: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)
    grammatical_range_accuracy: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)


class BaselineGradeResponse(BaseModel):
    """Structured response ordering rationale BEFORE final numeric criterion scores."""

    model_config = ConfigDict(extra="forbid")
    brief_rationale: str = Field(..., min_length=1)
    criterion_rationale: CriterionRationale
    criterion_scores: CriterionScorePayload


def format_fewshot_block(fewshot_pool: list[EssayRecord]) -> str:
    from app.grading.payload import project_anchor
    from app.grading.schemas import CRITERIA
    from src.eval.prompt_v1 import select_stratified_anchors
    return json.dumps([project_anchor({
        'question': r.prompt, 'student_essay': r.essay,
        'scores': dict(zip(CRITERIA, (r.tr, r.cc, r.lr, r.gra))),
        'score_source': r.score_source, 'score_provenance': r.score_provenance,
        'feedback_by_criterion': r.examiner_feedback,
        'metadata': {'paragraph_boundary_verified': r.paragraph_boundary_verified,
                     'paragraph_spans': r.paragraph_spans},
    }) for r in select_stratified_anchors(fewshot_pool)], ensure_ascii=False)


def build_user_prompt(target: EssayRecord, fewshot_pool: list[EssayRecord]) -> str:
    return build_user_prompt_v1(target, fewshot_pool)


class LiveGeminiScorer:
    """Live Gemini structured scorer conforming to EssayScorer protocol + telemetry logging."""

    def __init__(
        self,
        *,
        prompt_version: str = "v0",
        rpm: int | None = None,
        daily_budget: int | None = None,
        timeout: int | None = None,
        retries: int = 3,
    ) -> None:
        if prompt_version not in ("v0", "v1"):
            raise ValueError(f"Unsupported prompt_version: {prompt_version}")
        self.prompt_version = prompt_version
        base = load_settings()
        self.settings = replace(
            base,
            requests_per_minute=rpm if rpm is not None else base.requests_per_minute,
            daily_budget=daily_budget if daily_budget is not None else max(base.daily_budget, 300),
            timeout=timeout if timeout is not None else max(base.timeout, 60),
            retries=retries,
        )
        self.model_name = self.settings.model
        self.last_telemetry: dict[str, Any] = {}

    def cache_policy(self, pool):
        import hashlib
        from app.grading.payload import PAYLOAD_VERSION
        from src.eval.prompt_v1 import PROMPT_V1_VERSION
        serialized = json.dumps([r.model_dump() for r in pool], sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        return f'{PAYLOAD_VERSION}:floor_half_v1:{PROMPT_V1_VERSION}:{self.prompt_version}:{self.model_name}:{digest}'

    async def score_async(self, target: EssayRecord, fewshot_pool: list[EssayRecord], provider: GeminiProvider) -> dict[str, Any]:
        pool_ids = {e.essay_id for e in fewshot_pool}
        if target.essay_id in pool_ids:
            raise AssertionError(f"Target leakage detected: {target.essay_id} is inside fewshot_pool!")

        if self.prompt_version == "v1":
            sys_prompt = SYSTEM_PROMPT_V1
            user_prompt = build_user_prompt_v1(target, fewshot_pool)
        else:
            sys_prompt = SYSTEM_PROMPT
            user_prompt = build_user_prompt(target, fewshot_pool)
        gen = await provider.generate_structured(sys_prompt, user_prompt, BaselineGradeResponse)
        parsed = BaselineGradeResponse.model_validate_json(gen.raw)
        cs = parsed.criterion_scores
        tr = round_half(cs.task_response)
        cc = round_half(cs.coherence_cohesion)
        lr = round_half(cs.lexical_resource)
        gra = round_half(cs.grammatical_range_accuracy)
        ov = compute_ielts_overall(tr, cc, lr, gra)

        result = {
            "overall_policy": "floor_half_v1",
            "pred": {"tr": tr, "cc": cc, "lr": lr, "gra": gra, "overall": ov},
            "rationale": {
                "brief": parsed.brief_rationale,
                "criteria": parsed.criterion_rationale.model_dump(),
            },
            "latency_ms": gen.latency_ms,
            "usage": gen.usage,
            "model": getattr(gen, "version", None) or gen.model,
        }
        self.last_telemetry = result
        return result

    def score(self, target: EssayRecord, fewshot_pool: list[EssayRecord]) -> dict[str, float]:
        async def _once() -> dict[str, Any]:
            provider = GeminiProvider(self.settings)
            try:
                return await self.score_async(target, fewshot_pool, provider)
            finally:
                await provider.close()

        out = asyncio.run(_once())
        return out["pred"]
