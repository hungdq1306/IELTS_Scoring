"""13-fold Leave-One-Out Cross-Validation (Examiner-Calibration Audit) on examiner_verified essays."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from src.data.tiering import CRITERIA_KEYS, EssayRecord, compute_ielts_overall, round_half
from src.eval.metrics import evaluate_predictions, export_metrics, render_metrics_markdown


class EssayScorer(Protocol):
    """Interface for live or mock IELTS Writing Task 2 scorers used in LOO-CV."""

    def score(self, target: EssayRecord, fewshot_pool: list[EssayRecord]) -> dict[str, float]:
        """Return predicted scores dict with keys: tr, cc, lr, gra, overall."""
        ...


class DeterministicMockScorer:
    """Zero-cost deterministic mock scorer for end-to-end LOO-CV pipeline verification."""

    def __init__(self, random_seed: int = 42) -> None:
        self.random_seed = random_seed

    def score(self, target: EssayRecord, fewshot_pool: list[EssayRecord]) -> dict[str, float]:
        pool_ids = {e.essay_id for e in fewshot_pool}
        if target.essay_id in pool_ids:
            raise AssertionError(f"Target leakage detected: {target.essay_id} is inside fewshot_pool!")

        pool_mean_ov = sum(e.overall for e in fewshot_pool) / max(1, len(fewshot_pool))
        preds: dict[str, float] = {}
        for crit in CRITERIA_KEYS:
            true_val = float(getattr(target, crit))
            digest = hashlib.sha256(f"{self.random_seed}:{target.essay_id}:{crit}".encode("utf-8")).digest()
            bucket = digest[0] % 5
            if bucket == 0:
                delta = -0.5
            elif bucket == 4:
                delta = 0.5
            else:
                delta = 0.0
            raw = true_val + delta
            if true_val >= 8.5 and bucket in (0, 1):
                raw = min(raw, true_val - 0.5)
            elif true_val <= 5.0 and pool_mean_ov > 6.5 and bucket == 4:
                raw = max(raw, true_val + 0.5)
            preds[crit] = max(0.0, min(9.0, round_half(raw)))
        preds["overall"] = compute_ielts_overall(preds["tr"], preds["cc"], preds["lr"], preds["gra"])
        return preds


def load_examiner_verified_from_seed(seed_jsonl: Path) -> list[EssayRecord]:
    """Load strictly the 13 examiner_verified records from artifacts/dataset_v1/seed.jsonl."""
    records: list[EssayRecord] = []
    with seed_jsonl.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = EssayRecord.model_validate_json(line)
            if rec.quality_tier == "examiner_verified":
                records.append(rec)
    records.sort(key=lambda r: r.essay_id)
    return records


def _finalize_loo_report(
    *,
    eval_pairs: list[dict[str, Any]],
    fold_records: list[dict[str, Any]],
    out_dir: Path,
    mode_label: str,
    telemetry_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = evaluate_predictions(eval_pairs)
    report["mode"] = mode_label
    report["n_folds"] = len(fold_records)
    report["folds"] = fold_records
    if telemetry_summary is not None:
        report["telemetry"] = telemetry_summary

    ov = report["metrics"]["overall"]
    high_85 = ov["strata"]["high_tail_ge_8_5"]
    report["examiner_calibration_highlights"] = {
        "overall_qwk": ov["qwk"],
        "overall_qwk_ci_95": ov["qwk_ci_95"],
        "overall_micro_mae": ov["micro_mae"],
        "overall_macro_mae": ov["macro_mae"],
        "overall_smd": ov["smd"],
        "overall_sd_ratio": ov["sd_ratio"],
        "bands_8_5_to_9_0_n": high_85["n"],
        "bands_8_5_to_9_0_mae": high_85["mae"],
        "bands_8_5_to_9_0_mean_bias": high_85["mean_bias"],
    }

    json_path = out_dir / f"loo_audit_{mode_label}.json"
    md_path = out_dir / f"loo_audit_{mode_label}.md"
    export_metrics(
        report,
        json_path=json_path,
        md_path=md_path,
        title=f"Examiner-Calibration 13-Fold LOO-CV Audit ({mode_label})",
    )
    return report


def run_loo_audit(
    seed_jsonl: Path,
    scorer: EssayScorer,
    out_dir: Path,
    mode_label: str = "dry_run",
) -> dict[str, Any]:
    """Execute 13-fold Leave-One-Out Cross-Validation with zero target leakage (sync interface)."""
    examiner_essays = load_examiner_verified_from_seed(seed_jsonl)
    n_folds = len(examiner_essays)
    if n_folds != 13:
        raise ValueError(f"Expected exactly 13 examiner_verified essays in {seed_jsonl}, found {n_folds}")

    fold_records: list[dict[str, Any]] = []
    eval_pairs: list[dict[str, Any]] = []

    for fold_idx, target in enumerate(examiner_essays, start=1):
        fewshot_pool = [e for e in examiner_essays if e.essay_id != target.essay_id]
        assert len(fewshot_pool) == n_folds - 1
        assert target.essay_id not in {e.essay_id for e in fewshot_pool}

        pred = scorer.score(target, fewshot_pool)
        true_scores = {
            "tr": target.tr,
            "cc": target.cc,
            "lr": target.lr,
            "gra": target.gra,
            "overall": target.overall,
        }
        eval_pairs.append(
            {
                "essay_id": target.essay_id,
                "prompt_cluster_id": target.prompt_cluster_id or target.essay_id,
                "true": true_scores,
                "pred": pred,
            }
        )
        fold_records.append(
            {
                "fold": fold_idx,
                "target_essay_id": target.essay_id,
                "prompt_cluster_id": target.prompt_cluster_id,
                "fewshot_pool_size": len(fewshot_pool),
                "true": true_scores,
                "pred": pred,
                "overall_error": round(pred["overall"] - target.overall, 2),
            }
        )

    return _finalize_loo_report(
        eval_pairs=eval_pairs,
        fold_records=fold_records,
        out_dir=out_dir,
        mode_label=mode_label,
    )


async def run_loo_audit_live(
    seed_jsonl: Path,
    out_dir: Path,
    *,
    prompt_version: str = "v0",
    rpm: int | None = None,
    daily_budget: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Execute live 13-fold LOO-CV against Gemini with resumable JSONL checkpointing & telemetry."""
    from src.eval.live_scorer import LiveGeminiScorer
    from app.providers.gemini import GeminiProvider

    examiner_essays = load_examiner_verified_from_seed(seed_jsonl)
    n_folds = len(examiner_essays)
    if n_folds != 13:
        raise ValueError(f"Expected exactly 13 examiner_verified essays in {seed_jsonl}, found {n_folds}")

    out_dir.mkdir(parents=True, exist_ok=True)
    mode_label = f"live_{prompt_version}"
    ckpt_name = "loo_live_predictions.jsonl" if prompt_version == "v0" else f"loo_{mode_label}_predictions.jsonl"
    ckpt_path = out_dir / ckpt_name
    cached: dict[str, dict[str, Any]] = {}
    if resume and ckpt_path.exists():
        with ckpt_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    cached[rec["target_essay_id"]] = rec

    scorer = LiveGeminiScorer(prompt_version=prompt_version, rpm=rpm, daily_budget=daily_budget)
    provider = GeminiProvider(scorer.settings)
    fold_records: list[dict[str, Any]] = []
    eval_pairs: list[dict[str, Any]] = []

    try:
        for fold_idx, target in enumerate(examiner_essays, start=1):
            fewshot_pool = [e for e in examiner_essays if e.essay_id != target.essay_id]
            assert len(fewshot_pool) == n_folds - 1
            assert target.essay_id not in {e.essay_id for e in fewshot_pool}

            true_scores = {
                "tr": target.tr,
                "cc": target.cc,
                "lr": target.lr,
                "gra": target.gra,
                "overall": target.overall,
            }

            if target.essay_id in cached:
                rec = cached[target.essay_id]
                print(
                    f"[LOO {fold_idx:02d}/13] CACHED {target.essay_id} | true={target.overall:g} pred={rec['pred']['overall']:g}",
                    flush=True,
                )
            else:
                res = await scorer.score_async(target, fewshot_pool, provider)
                rec = {
                    "fold": fold_idx,
                    "target_essay_id": target.essay_id,
                    "prompt_cluster_id": target.prompt_cluster_id,
                    "fewshot_pool_size": len(fewshot_pool),
                    "true": true_scores,
                    "pred": res["pred"],
                    "overall_error": round(res["pred"]["overall"] - target.overall, 2),
                    "rationale": res["rationale"],
                    "latency_ms": res["latency_ms"],
                    "usage": res["usage"],
                    "model": res["model"],
                }
                with ckpt_path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(
                    f"[LOO {fold_idx:02d}/13] LIVE {target.essay_id} | true={target.overall:g} pred={res['pred']['overall']:g} "
                    f"err={rec['overall_error']:+.1f} | {res['latency_ms']}ms | tok={res['usage'].get('total_token_count', 0)}",
                    flush=True,
                )

            fold_records.append(rec)
            eval_pairs.append(
                {
                    "essay_id": target.essay_id,
                    "prompt_cluster_id": target.prompt_cluster_id or target.essay_id,
                    "true": true_scores,
                    "pred": rec["pred"],
                }
            )
    finally:
        await provider.close()

    latencies = [int(r.get("latency_ms", 0)) for r in fold_records]
    prompt_toks = [int(r.get("usage", {}).get("prompt_token_count", 0)) for r in fold_records]
    cand_toks = [int(r.get("usage", {}).get("candidates_token_count", 0)) for r in fold_records]
    total_toks = [int(r.get("usage", {}).get("total_token_count", 0)) for r in fold_records]
    telemetry = {
        "model": fold_records[0].get("model") if fold_records else scorer.model_name,
        "mean_latency_ms": round(sum(latencies) / max(1, len(latencies)), 1),
        "total_prompt_tokens": sum(prompt_toks),
        "total_candidates_tokens": sum(cand_toks),
        "total_tokens": sum(total_toks),
    }

    return _finalize_loo_report(
        eval_pairs=eval_pairs,
        fold_records=fold_records,
        out_dir=out_dir,
        mode_label=mode_label,
        telemetry_summary=telemetry,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 13-fold LOO-CV Examiner-Calibration Audit.")
    parser.add_argument("--seed-jsonl", type=Path, default=Path("artifacts/dataset_v1/seed.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/dataset_v1/baseline_v0"))
    parser.add_argument("--dry-run", action="store_true", help="Run zero-cost deterministic mock scorer.")
    parser.add_argument("--live", action="store_true", help="Run live Gemini scorer with checkpointing.")
    parser.add_argument("--prompt-version", choices=("v0", "v1"), default="v0")
    parser.add_argument("--rpm", type=int, default=None, help="Optional RPM override for live scoring.")
    parser.add_argument("--daily-budget", type=int, default=None, help="Optional local daily budget override.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing checkpoint file.")
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()

    if args.dry_run:
        report = run_loo_audit(
            args.seed_jsonl,
            scorer=DeterministicMockScorer(random_seed=args.random_seed),
            out_dir=args.out_dir,
            mode_label="dry_run",
        )
        mode_label = "dry_run"
    elif args.live:
        report = asyncio.run(
            run_loo_audit_live(
                args.seed_jsonl,
                out_dir=args.out_dir,
                prompt_version=args.prompt_version,
                rpm=args.rpm,
                daily_budget=args.daily_budget,
                resume=not args.no_resume,
            )
        )
        mode_label = f"live_{args.prompt_version}"
    else:
        parser.error("Specify either --dry-run or --live")
        return

    print(render_metrics_markdown(report, title=f"Examiner-Calibration 13-Fold LOO-CV Audit ({mode_label})"))
    print("Examiner-Calibration Highlights:")
    print(json.dumps(report["examiner_calibration_highlights"], indent=2))


if __name__ == "__main__":
    main()
