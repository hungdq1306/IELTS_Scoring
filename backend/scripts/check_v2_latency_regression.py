"""Dev-only latency and TR/CC drift check for trimmed V2 + thinking_budget + FEEDBACK_LANGUAGE=vi.

Strictly targets artifacts/dataset_v1/dev.jsonl and refuses any Holdout dataset path.
Run offline smoke check:
  python backend/scripts/check_v2_latency_regression.py --dry-run --limit 6
Run live check against Gemini (requires GEMINI_API_KEY in env/.env):
  python backend/scripts/check_v2_latency_regression.py --limit 6
"""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings
from app.grading.v2 import AssessmentOutputV2
from app.providers.base import Generation
from app.providers.gemini import GeminiProvider
from app.services.scorer import baseline_config, score


DEFAULT_DEV_PATH = ROOT / "artifacts" / "dataset_v1" / "dev.jsonl"


def load_stratified_dev_essays(path: Path, limit: int) -> list[dict]:
    if "holdout" in str(path).lower():
        raise ValueError("Refusing to read Holdout dataset; Dev-only script.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit >= len(rows):
        return rows
    ordered = sorted(rows, key=lambda r: (float(r.get("overall", 0)), r["essay_id"]))
    step = len(ordered) / limit
    return [ordered[min(len(ordered) - 1, int(i * step))] for i in range(limit)]


class DryRunProvider:
    """Offline fixture provider preserving ground truth bands for pipeline verification."""

    def __init__(self, row: dict, feedback_language: str):
        self.row = row
        self.settings = SimpleNamespace(feedback_language=feedback_language, score_thinking_budget=512)

    async def generate_structured(self, system, user, response_schema):
        assert response_schema is AssessmentOutputV2
        if self.settings.feedback_language == "vi":
            assert "FEEDBACK_LANGUAGE=vi" in system
        feedback_text = (
            "Ý chính rõ ràng nhưng cần thêm ví dụ cụ thể hơn."
            if self.settings.feedback_language == "vi"
            else "Clear position; develop supporting examples further."
        )
        criterion = {
            "explanation": feedback_text,
            "strengths": [feedback_text],
            "weaknesses": [feedback_text],
            "evidence": [],
        }
        payload = {
            "structural_audit": {
                "prompt_subtasks_addressed": ["Full: task addressed cleanly."],
                "paragraph_core_claims": ["Main argument stated."],
                "circular_or_padding_flags": [],
                "cohesion_faults": [],
            },
            "tr_reasoning": "Addresses prompt with relevant ideas.",
            "tr_score": float(self.row["tr"]),
            "cc_reasoning": "Logical progression across paragraphs.",
            "cc_score": float(self.row["cc"]),
            "lr_reasoning": "Adequate lexical precision.",
            "lr_score": float(self.row["lr"]),
            "gra_reasoning": "Mix of simple and complex clauses.",
            "gra_score": float(self.row["gra"]),
            "criterion_feedback": {
                "task_response": criterion,
                "coherence_cohesion": criterion,
                "lexical_resource": criterion,
                "grammatical_range_accuracy": criterion,
            },
            "sentence_annotations": [],
            "top_weaknesses": [feedback_text],
            "grammar_corrections": [],
            "aspect_reviews": [],
            "paragraph_reviews": [],
            "language_suggestions": [],
        }
        return Generation(
            json.dumps(payload, ensure_ascii=False),
            "dry-run",
            None,
            120,
            {"thoughts_token_count": 384, "candidates_token_count": 420, "total_token_count": 1800},
            [],
        )


async def evaluate_dev(limit: int, dev_path: Path, thinking_budget: int, feedback_language: str, dry_run: bool) -> int:
    rows = load_stratified_dev_essays(dev_path, limit)
    fewshot = baseline_config()
    settings = load_settings()
    provider = None
    if not dry_run:
        if not settings.api_key:
            raise RuntimeError("GEMINI_API_KEY is required unless --dry-run is set.")
        from dataclasses import replace
        provider = GeminiProvider(
            replace(settings, score_thinking_budget=thinking_budget, feedback_language=feedback_language)
        )

    results = []
    try:
        for row in rows:
            submission = SimpleNamespace(
                prompt=row["prompt"],
                essay=row["essay"],
                warnings=[],
                config_snapshot={
                    "fewshot": fewshot,
                    "prompt_version": "v2",
                    "feedback_language": feedback_language,
                },
            )
            active_provider = DryRunProvider(row, feedback_language) if dry_run else provider
            out = await score(submission, active_provider)
            pred = out["criterion_scores"]
            tr_drift = round(float(pred["task_response"]) - float(row["tr"]), 2)
            cc_drift = round(float(pred["coherence_cohesion"]) - float(row["cc"]), 2)
            ov_drift = round(float(out["estimated_overall_band"]) - float(row["overall"]), 2)
            item = {
                "essay_id": row["essay_id"],
                "latency_ms": out["latency_ms"],
                "human": {"tr": row["tr"], "cc": row["cc"], "overall": row["overall"]},
                "pred": {
                    "tr": pred["task_response"],
                    "cc": pred["coherence_cohesion"],
                    "overall": out["estimated_overall_band"],
                },
                "drift": {"tr": tr_drift, "cc": cc_drift, "overall": ov_drift},
            }
            results.append(item)
            print(json.dumps(item, ensure_ascii=False))
    finally:
        if provider is not None:
            await provider.close()

    n = max(1, len(results))
    summary = {
        "count": len(results),
        "dataset": str(dev_path),
        "thinking_budget": thinking_budget,
        "feedback_language": feedback_language,
        "dry_run": dry_run,
        "mean_latency_ms": round(sum(r["latency_ms"] for r in results) / n, 1),
        "tr_mae": round(sum(abs(r["drift"]["tr"]) for r in results) / n, 3),
        "cc_mae": round(sum(abs(r["drift"]["cc"]) for r in results) / n, 3),
        "overall_mae": round(sum(abs(r["drift"]["overall"]) for r in results) / n, 3),
        "max_abs_tr_drift": max(abs(r["drift"]["tr"]) for r in results),
        "max_abs_cc_drift": max(abs(r["drift"]["cc"]) for r in results),
    }
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev-only V2 latency and TR/CC drift check.")
    parser.add_argument("--dev-path", type=Path, default=DEFAULT_DEV_PATH)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--thinking-budget", type=int, default=512)
    parser.add_argument("--feedback-language", choices=("vi", "en"), default="vi")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("--limit must be between 1 and 10 for Dev spot checks.")
    return asyncio.run(
        evaluate_dev(args.limit, args.dev_path, args.thinking_budget, args.feedback_language, args.dry_run)
    )


if __name__ == "__main__":
    raise SystemExit(main())
