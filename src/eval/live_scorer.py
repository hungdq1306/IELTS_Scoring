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
    """Format calibration anchor essays deterministically ordered from lowest to highest band."""
    ordered = sorted(fewshot_pool, key=lambda r: (r.overall, r.essay_id))
    parts = [
        "=== CALIBRATION REFERENCE ANCHORS (OFFICIAL BAND SCALE 4.5 - 9.0) ===",
        "Use these verified anchor essays to calibrate your strictness and ceiling/floor scores.",
    ]
    for idx, ex in enumerate(ordered, start=1):
        parts.append(
            f"\n[Anchor {idx} | Tier={ex.quality_tier} | TR={ex.tr:g}, CC={ex.cc:g}, LR={ex.lr:g}, GRA={ex.gra:g}, Overall={ex.overall:g}]\n"
            f"Prompt: {ex.prompt}\n"
            f"Essay ({ex.word_count} words): {ex.essay}"
        )
    parts.append("\n=== END OF CALIBRATION ANCHORS ===")
    return "\n".join(parts)


def build_user_prompt(target: EssayRecord, fewshot_pool: list[EssayRecord]) -> str:
    anchors = format_fewshot_block(fewshot_pool)
    payload = {
        "prompt": target.prompt,
        "essay": target.essay,
        "word_count": target.word_count,
        "length_note": "Under 250 words — evaluate Task Response development strictly." if target.word_count < 250 else "Meets 250+ word expectation.",
    }
    return (
        f"{anchors}\n\n"
        "Now assess the following target IELTS Writing Task 2 essay independently against the May 2023 official rubric "
        "and the calibration anchors above. Provide concise criterion rationales BEFORE locking criterion_scores "
        "in 0.5-band increments.\n\n"
        f"TARGET_ESSAY_JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )


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
