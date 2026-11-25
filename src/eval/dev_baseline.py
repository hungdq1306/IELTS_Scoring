"""Live Baseline v0 evaluation runner on frozen dataset_v1 Dev split (173 essays)."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from src.data.tiering import EssayRecord
from src.eval.metrics import evaluate_predictions, export_metrics, render_metrics_markdown


def _load_jsonl(path: Path) -> list[EssayRecord]:
    from src.data.records import load_records
    return load_records(path)


def _band_error_table(eval_pairs: list[dict[str, Any]]) -> str:
    by_band: dict[float, list[float]] = defaultdict(list)
    for item in eval_pairs:
        t = float(item["true"]["overall"])
        p = float(item["pred"]["overall"])
        by_band[t].append(p - t)
    lines = [
        "",
        "## Per-Band Overall Error & Bias Diagnosis",
        "",
        "| True Overall Band | N | MAE | Mean Bias (`pred - true`) | Exact (%) | Adjacent <=0.5 (%) |",
        "|:---:|---:|---:|---:|---:|---:|",
    ]
    for band in sorted(by_band.keys()):
        errs = by_band[band]
        n = len(errs)
        mae = sum(abs(e) for e in errs) / n
        bias = sum(errs) / n
        exact = 100.0 * sum(1 for e in errs if e == 0.0) / n
        adj = 100.0 * sum(1 for e in errs if abs(e) <= 0.5) / n
        lines.append(f"| **{band:.1f}** | {n} | {mae:.4f} | {bias:+.4f} | {exact:.1f}% | {adj:.1f}% |")
    return "\n".join(lines) + "\n"


async def run_dev_baseline_live(
    *,
    seed_jsonl: Path,
    dev_jsonl: Path,
    out_dir: Path,
    prompt_version: str = "v0",
    rpm: int | None = None,
    daily_budget: int | None = None,
    max_essays: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    from src.eval.live_scorer import LiveGeminiScorer
    from app.providers.gemini import GeminiProvider

    seed_pool = _load_jsonl(seed_jsonl)
    dev_rows = _load_jsonl(dev_jsonl)
    if max_essays is not None:
        dev_rows = dev_rows[:max_essays]

    # Strict zero-overlap guard between Seed and Dev
    seed_ids = {r.essay_id for r in seed_pool}
    assert seed_ids.isdisjoint({r.essay_id for r in dev_rows}), "Seed/Dev essay_id overlap detected!"

    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_name = "dev_live_predictions.jsonl" if prompt_version == "v0" else f"dev_live_predictions_{prompt_version}.jsonl"
    ckpt_path = out_dir / ckpt_name
    if not resume and ckpt_path.exists() and ckpt_path.stat().st_size:
        raise ValueError('Choose a new output directory for a fresh evaluation')
    cached: dict[str, dict[str, Any]] = {}
    if resume and ckpt_path.exists():
        with ckpt_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    cached[rec["essay_id"]] = rec

    scorer = LiveGeminiScorer(prompt_version=prompt_version, rpm=rpm, daily_budget=daily_budget)
    policy = scorer.cache_policy(seed_pool)
    if any(record.get('cache_policy') != policy for record in cached.values()):
        raise ValueError('Cached predictions use a different prompt/data/overall policy; choose a new output directory')
    provider = GeminiProvider(scorer.settings)
    records: list[dict[str, Any]] = []
    eval_pairs: list[dict[str, Any]] = []
    total = len(dev_rows)

    try:
        for idx, target in enumerate(dev_rows, start=1):
            true_scores = {
                "tr": target.tr,
                "cc": target.cc,
                "lr": target.lr,
                "gra": target.gra,
                "overall": target.overall,
            }
            if target.essay_id in cached:
                rec = cached[target.essay_id]
            else:
                res = await scorer.score_async(target, seed_pool, provider)
                rec = {
                    "essay_id": target.essay_id,
                    "prompt_cluster_id": target.prompt_cluster_id,
                    "quality_tier": target.quality_tier,
                    "true": true_scores,
                    "pred": res["pred"],
                    "overall_error": round(res["pred"]["overall"] - target.overall, 2),
                    "rationale": res["rationale"],
                    "cache_policy": policy, "overall_policy": "floor_half_v1",
                    "latency_ms": res["latency_ms"],
                    "usage": res["usage"],
                    "model": res["model"],
                }
                with ckpt_path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if idx <= 5 or idx % 10 == 0 or idx == total:
                    print(
                        f"[DEV {idx:03d}/{total}] LIVE {target.essay_id} | true={target.overall:g} pred={res['pred']['overall']:g} "
                        f"err={rec['overall_error']:+.1f} | {res['latency_ms']}ms | tok={res['usage'].get('total_token_count', 0)}",
                        flush=True,
                    )
            records.append(rec)
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

    report = evaluate_predictions(eval_pairs)
    latencies = [int(r.get("latency_ms", 0)) for r in records]
    prompt_toks = [int(r.get("usage", {}).get("prompt_token_count", 0)) for r in records]
    cand_toks = [int(r.get("usage", {}).get("candidates_token_count", 0)) for r in records]
    total_toks = [int(r.get("usage", {}).get("total_token_count", 0)) for r in records]
    report["telemetry"] = {
        "model": records[0].get("model") if records else scorer.model_name,
        "seed_pool_size": len(seed_pool),
        "dev_evaluated": len(records),
        "mean_latency_ms": round(sum(latencies) / max(1, len(latencies)), 1),
        "p95_latency_ms": sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else 0,
        "total_prompt_tokens": sum(prompt_toks),
        "total_candidates_tokens": sum(cand_toks),
        "total_tokens": sum(total_toks),
    }

    # Diagnostic ranking of criteria by Micro-MAE (worst first)
    crit_ranking = sorted(
        ((k, report["metrics"][k]["micro_mae"], report["metrics"][k]["qwk"], report["metrics"][k]["mean_bias"]) for k in ("tr", "cc", "lr", "gra")),
        key=lambda x: -x[1],
    )
    report["worst_criteria_by_mae"] = [
        {"criterion": k, "micro_mae": mae, "qwk": qwk, "mean_bias": bias} for k, mae, qwk, bias in crit_ranking
    ]

    stem = "dev_baseline_v0" if prompt_version == "v0" else f"dev_candidate_{prompt_version}"
    title = (
        "Live Baseline v0 — Frozen Dev Split (173 Essays)"
        if prompt_version == "v0"
        else f"Live Candidate {prompt_version} — Frozen Dev Split (173 Essays)"
    )
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    export_metrics(report, json_path=json_path, md_path=None)
    md = render_metrics_markdown(report, title=title)
    md += _band_error_table(eval_pairs)
    md += (
        "\n## Telemetry Summary\n"
        f"- **Prompt Version:** `{prompt_version}`\n"
        f"- **Model:** `{report['telemetry']['model']}`\n"
        f"- **Mean / P95 Latency:** `{report['telemetry']['mean_latency_ms']} ms` / `{report['telemetry']['p95_latency_ms']} ms`\n"
        f"- **Tokens (Prompt / Output / Total):** `{report['telemetry']['total_prompt_tokens']:,}` / "
        f"`{report['telemetry']['total_candidates_tokens']:,}` / `{report['telemetry']['total_tokens']:,}`\n"
    )
    md_path.write_text(md, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Live evaluation on frozen dataset_v1 Dev split.")
    parser.add_argument("--seed-jsonl", type=Path, default=Path("artifacts/dataset_v1/seed.jsonl"))
    parser.add_argument("--dev-jsonl", type=Path, default=Path("artifacts/dataset_v1/dev.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/dataset_v1/baseline_v0"))
    parser.add_argument("--prompt-version", choices=("v0", "v1"), default="v0")
    parser.add_argument("--rpm", type=int, default=None, help="Optional RPM override.")
    parser.add_argument("--daily-budget", type=int, default=None, help="Optional local daily request budget override.")
    parser.add_argument("--max-essays", type=int, default=None, help="Optional cap for bounded smoke test.")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    asyncio.run(
        run_dev_baseline_live(
            seed_jsonl=args.seed_jsonl,
            dev_jsonl=args.dev_jsonl,
            out_dir=args.out_dir,
            prompt_version=args.prompt_version,
            rpm=args.rpm,
            daily_budget=args.daily_budget,
            max_essays=args.max_essays,
            resume=not args.no_resume,
        )
    )
    stem = "dev_baseline_v0" if args.prompt_version == "v0" else f"dev_candidate_{args.prompt_version}"
    print((args.out_dir / f"{stem}.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
