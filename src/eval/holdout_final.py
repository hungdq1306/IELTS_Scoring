"""Final One-Shot Holdout Evaluation (v0_raw vs v1_raw vs v1_cc_offset) with Paired Clustered Bootstrap test."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.data.tiering import EssayRecord, compute_ielts_overall, round_half
from src.eval.metrics import (
    DEFAULT_BOOTSTRAP_ITERS,
    DEFAULT_BOOTSTRAP_SEED,
    TARGET_KEYS,
    _fast_qwk_classes,
    evaluate_predictions,
    macro_mae,
    to_band_class,
)


def _load_essays(path: Path) -> list[EssayRecord]:
    from src.data.records import load_records
    return load_records(path)


def _load_preds(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["essay_id"])
    return rows


def freeze_dev_cc_calibration(
    dev_v1_preds_path: Path,
    out_json_path: Path,
) -> dict[str, Any]:
    """Compute single deterministic CC additive offset strictly on policy-compatible frozen Dev predictions."""
    dev_rows = _load_preds(dev_v1_preds_path)
    from src.data.records import load_records, check_membership
    dataset_dir = Path(__file__).resolve().parents[2] / 'artifacts/dataset_v1'
    expected = load_records(dataset_dir / 'dev.jsonl')
    check_membership(expected, 'dev', dataset_dir)
    if len(dev_rows) != len(expected) or {r['essay_id'] for r in dev_rows} != {r.essay_id for r in expected}:
        raise ValueError('Dev predictions differ from frozen Dev membership')
    if any(r.get('overall_policy') != 'floor_half_v1' for r in dev_rows):
        raise ValueError('Dev calibration requires predictions with the current scoring policy')
    cc_diffs = [float(r["true"]["cc"]) - float(r["pred"]["cc"]) for r in dev_rows]
    cc_offset = float(np.mean(cc_diffs))
    payload = {
        "source": str(dev_v1_preds_path),
        "n_dev_essays": len(dev_rows),
        "cc_additive_offset": round(cc_offset, 6),
        "note": "Learned strictly on frozen Dev predictions. Zero Holdout parameters fitted.",
    }
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


async def _run_one_shot_holdout_version(
    *,
    prompt_version: str,
    seed_pool: list[EssayRecord],
    holdout_rows: list[EssayRecord],
    ckpt_path: Path,
    rpm: int | None,
    daily_budget: int | None,
    resume: bool = True,
) -> list[dict[str, Any]]:
    from src.eval.live_scorer import LiveGeminiScorer
    from app.providers.gemini import GeminiProvider

    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    if not resume and ckpt_path.exists() and ckpt_path.stat().st_size:
        raise ValueError('Choose a new output directory for a fresh evaluation')
    cached: dict[str, dict[str, Any]] = {}
    if resume and ckpt_path.exists():
        for rec in _load_preds(ckpt_path):
            cached[rec["essay_id"]] = rec

    scorer = LiveGeminiScorer(prompt_version=prompt_version, rpm=rpm, daily_budget=daily_budget)
    policy = scorer.cache_policy(seed_pool)
    if any(record.get('cache_policy') != policy for record in cached.values()):
        raise ValueError('Cached predictions use a different prompt/data/overall policy; choose a new output directory')
    provider = GeminiProvider(scorer.settings)
    records: list[dict[str, Any]] = []
    total = len(holdout_rows)

    try:
        for idx, target in enumerate(holdout_rows, start=1):
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
                if idx <= 3 or idx % 10 == 0 or idx == total:
                    print(
                        f"[HOLDOUT {prompt_version} {idx:02d}/{total}] LIVE {target.essay_id} | "
                        f"true={target.overall:g} pred={res['pred']['overall']:g} err={rec['overall_error']:+.1f} | "
                        f"{res['latency_ms']}ms | tok={res['usage'].get('total_token_count', 0)}",
                        flush=True,
                    )
            records.append(rec)
    finally:
        await provider.close()

    records.sort(key=lambda r: r["essay_id"])
    return records


def apply_frozen_cc_offset(v1_records: list[dict[str, Any]], cc_offset: float) -> list[dict[str, Any]]:
    """Apply frozen Dev CC additive offset to v1 Holdout predictions without touching TR, LR, GRA."""
    calibrated: list[dict[str, Any]] = []
    for r in v1_records:
        p = dict(r["pred"])
        new_cc = max(0.0, min(9.0, round_half(float(p["cc"]) + cc_offset)))
        p["cc"] = new_cc
        p["overall"] = compute_ielts_overall(float(p["tr"]), new_cc, float(p["lr"]), float(p["gra"]))
        calibrated.append(
            {
                "essay_id": r["essay_id"],
                "prompt_cluster_id": r["prompt_cluster_id"],
                "true": r["true"],
                "pred": p,
            }
        )
    return calibrated


def paired_clustered_bootstrap_test(
    v0_records: list[dict[str, Any]],
    v1_records: list[dict[str, Any]],
    *,
    n_boot: int = DEFAULT_BOOTSTRAP_ITERS,
    random_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Paired Clustered Bootstrap test (1,000 cluster resamples) for Delta QWK and Delta Macro-MAE (v1 - v0)."""
    assert [r["essay_id"] for r in v0_records] == [r["essay_id"] for r in v1_records]
    y_true = np.asarray([float(r["true"]["overall"]) for r in v0_records], dtype=np.float64)
    y_v0 = np.asarray([float(r["pred"]["overall"]) for r in v0_records], dtype=np.float64)
    y_v1 = np.asarray([float(r["pred"]["overall"]) for r in v1_records], dtype=np.float64)

    t_cls = np.asarray([to_band_class(v) for v in y_true], dtype=np.int64)
    v0_cls = np.asarray([to_band_class(v) for v in y_v0], dtype=np.int64)
    v1_cls = np.asarray([to_band_class(v) for v in y_v1], dtype=np.int64)

    obs_qwk_v0 = _fast_qwk_classes(t_cls, v0_cls)
    obs_qwk_v1 = _fast_qwk_classes(t_cls, v1_cls)
    obs_delta_qwk = obs_qwk_v1 - obs_qwk_v0

    obs_mmae_v0 = macro_mae(y_true, y_v0)
    obs_mmae_v1 = macro_mae(y_true, y_v1)
    obs_delta_mmae = obs_mmae_v1 - obs_mmae_v0

    obs_umae_v0 = float(np.mean(np.abs(y_v0 - y_true)))
    obs_umae_v1 = float(np.mean(np.abs(y_v1 - y_true)))
    obs_delta_umae = obs_umae_v1 - obs_umae_v0

    by_cluster: dict[str, list[int]] = defaultdict(list)
    for idx, r in enumerate(v0_records):
        by_cluster[str(r["prompt_cluster_id"])].append(idx)

    ordered_clusters = [np.asarray(by_cluster[k], dtype=np.int64) for k in sorted(by_cluster.keys())]
    k_clusters = len(ordered_clusters)
    rng = np.random.default_rng(random_seed)

    delta_qwk_samples = np.empty(n_boot, dtype=np.float64)
    delta_mmae_samples = np.empty(n_boot, dtype=np.float64)
    delta_umae_samples = np.empty(n_boot, dtype=np.float64)

    for b in range(n_boot):
        drawn = rng.integers(0, k_clusters, size=k_clusters)
        idxs = np.concatenate([ordered_clusters[c] for c in drawn])
        q0 = _fast_qwk_classes(t_cls[idxs], v0_cls[idxs])
        q1 = _fast_qwk_classes(t_cls[idxs], v1_cls[idxs])
        delta_qwk_samples[b] = q1 - q0

        m0 = macro_mae(y_true[idxs], y_v0[idxs])
        m1 = macro_mae(y_true[idxs], y_v1[idxs])
        delta_mmae_samples[b] = m1 - m0

        u0 = float(np.mean(np.abs(y_v0[idxs] - y_true[idxs])))
        u1 = float(np.mean(np.abs(y_v1[idxs] - y_true[idxs])))
        delta_umae_samples[b] = u1 - u0

    q_lo, q_hi = np.percentile(delta_qwk_samples, [2.5, 97.5])
    m_lo, m_hi = np.percentile(delta_mmae_samples, [2.5, 97.5])
    u_lo, u_hi = np.percentile(delta_umae_samples, [2.5, 97.5])

    # One-sided & two-sided empirical bootstrap p-values
    # For QWK: H1 is delta > 0 -> p_one_sided = mean(delta <= 0)
    p_qwk_one = float(np.mean(delta_qwk_samples <= 0.0))
    p_qwk_two = min(1.0, 2.0 * min(float(np.mean(delta_qwk_samples <= 0.0)), float(np.mean(delta_qwk_samples >= 0.0))))

    # For Macro-MAE & Micro-MAE: H1 is delta < 0 (error reduction) -> p_one_sided = mean(delta >= 0)
    p_mmae_one = float(np.mean(delta_mmae_samples >= 0.0))
    p_mmae_two = min(1.0, 2.0 * min(float(np.mean(delta_mmae_samples >= 0.0)), float(np.mean(delta_mmae_samples <= 0.0))))

    p_umae_one = float(np.mean(delta_umae_samples >= 0.0))
    p_umae_two = min(1.0, 2.0 * min(float(np.mean(delta_umae_samples >= 0.0)), float(np.mean(delta_umae_samples <= 0.0))))

    return {
        "n_clusters": k_clusters,
        "n_boot": n_boot,
        "delta_qwk": {
            "observed": round(float(obs_delta_qwk), 4),
            "ci_95": [round(float(q_lo), 4), round(float(q_hi), 4)],
            "p_one_sided": round(p_qwk_one, 4),
            "p_two_sided": round(p_qwk_two, 4),
        },
        "delta_macro_mae": {
            "observed": round(float(obs_delta_mmae), 4),
            "ci_95": [round(float(m_lo), 4), round(float(m_hi), 4)],
            "p_one_sided": round(p_mmae_one, 4),
            "p_two_sided": round(p_mmae_two, 4),
        },
        "delta_micro_mae": {
            "observed": round(float(obs_delta_umae), 4),
            "ci_95": [round(float(u_lo), 4), round(float(u_hi), 4)],
            "p_one_sided": round(p_umae_one, 4),
            "p_two_sided": round(p_umae_two, 4),
        },
    }


def _telemetry(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lats = [int(r.get("latency_ms", 0)) for r in rows]
    ptoks = [int(r.get("usage", {}).get("prompt_token_count", 0)) for r in rows]
    ctoks = [int(r.get("usage", {}).get("candidates_token_count", 0)) for r in rows]
    ttoks = [int(r.get("usage", {}).get("total_token_count", 0)) for r in rows]
    n = max(1, len(rows))
    return {
        "mean_latency_ms": round(sum(lats) / n, 1),
        "p95_latency_ms": sorted(lats)[int(0.95 * (len(lats) - 1))] if lats else 0,
        "mean_tokens": round(sum(ttoks) / n, 1),
        "total_prompt_tokens": sum(ptoks),
        "total_output_tokens": sum(ctoks),
        "total_tokens": sum(ttoks),
    }


def _fmt_metric_row(label: str, m: dict[str, Any]) -> str:
    q_lo, q_hi = m["qwk_ci_95"]
    u_lo, u_hi = m["micro_mae_ci_95"]
    q_flag = "PASS" if m["qwk_pass"] else "FAIL"
    s_flag = "PASS" if m["smd_pass"] else "FAIL"
    r_flag = "PASS" if m["sd_ratio_pass"] else "FAIL"
    sdr_s = f"`{m['sd_ratio']:.3f}` ({r_flag})" if m["sd_ratio"] is not None else "N/A"
    return (
        f"| {label} | `{m['qwk']:.4f}` [{q_lo:.3f}, {q_hi:.3f}] ({q_flag}) | "
        f"{m['micro_mae']:.4f} [{u_lo:.3f}, {u_hi:.3f}] | {m['macro_mae']:.4f} | "
        f"{m['mean_bias']:+.4f} | `{m['smd']:+.4f}` ({s_flag}) | {sdr_s} | "
        f"{m['exact_agreement_pct']:.1f}% | {m['adjacent_agreement_pct']:.1f}% |"
    )


async def run_final_holdout_evaluation(
    *,
    seed_jsonl: Path,
    holdout_jsonl: Path,
    dev_v1_preds: Path,
    out_dir: Path,
    rpm: int | None = None,
    daily_budget: int | None = None,
    resume: bool = True,
) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    seed_pool = _load_essays(seed_jsonl)
    holdout_rows = _load_essays(holdout_jsonl)

    # Verify frozen membership and clusters, tier purity, and zero Seed overlap.
    from src.data.records import check_membership
    check_membership(holdout_rows, 'holdout', holdout_jsonl.parent)
    assert {r.quality_tier for r in holdout_rows} == {"max2_half"}
    assert {r.essay_id for r in seed_pool}.isdisjoint({r.essay_id for r in holdout_rows})

    # 1. Freeze Dev-learned CC offset
    cal_payload = freeze_dev_cc_calibration(dev_v1_preds, out_dir / "dev_frozen_calibration.json")
    cc_offset = float(cal_payload["cc_additive_offset"])

    # 2. Run one-shot live scoring on holdout.jsonl for v0_raw and v1_raw
    v0_records = await _run_one_shot_holdout_version(
        prompt_version="v0",
        seed_pool=seed_pool,
        holdout_rows=holdout_rows,
        ckpt_path=out_dir / "holdout_predictions_v0.jsonl",
        rpm=rpm,
        daily_budget=daily_budget,
        resume=resume,
    )
    v1_records = await _run_one_shot_holdout_version(
        prompt_version="v1",
        seed_pool=seed_pool,
        holdout_rows=holdout_rows,
        ckpt_path=out_dir / "holdout_predictions_v1.jsonl",
        rpm=rpm,
        daily_budget=daily_budget,
        resume=resume,
    )

    v1_cc_records = apply_frozen_cc_offset(v1_records, cc_offset=cc_offset)

    rep_v0 = evaluate_predictions(v0_records)
    rep_v1 = evaluate_predictions(v1_records)
    rep_v1_cc = evaluate_predictions(v1_cc_records)

    paired_test = paired_clustered_bootstrap_test(v0_records, v1_records)
    t_v0 = _telemetry(v0_records)
    t_v1 = _telemetry(v1_records)

    lines: list[str] = [
        "# Final One-Shot Holdout Evaluation Report (`dataset_v1` — 63 Essays, 47 Clusters, 100% `max2_half`)",
        "",
        f"- **Holdout Set:** `63` essays across `47` independent prompt clusters (`100% max2_half`, zero prompt overlap `< 0.60` with `Seed` and `Dev`).",
        f"- **Frozen Dev Calibration (`dev_frozen_calibration.json`):** `cc_additive_offset = {cc_offset:+.4f}` (learned strictly on 173 Dev essays; `0` parameters fitted on Holdout).",
        f"- **Benchmarks:** `QWK >= 0.70`, `|SMD| <= 0.15`, `SD Ratio in [0.67, 1.50]`, Clustered Bootstrap 95% CI (`1,000` cluster resamples).",
        "",
        "## 1. Overall & Per-Criterion Psychometric Comparison (`v0_raw` vs `v1_raw` vs `v1_cc_offset`)",
        "",
        "| Dimension / Variant | QWK [95% CI] | Micro-MAE [95% CI] | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for key in TARGET_KEYS:
        dim = key.upper()
        lines.append(_fmt_metric_row(f"**{dim}** — `v0_raw`", rep_v0["metrics"][key]))
        lines.append(_fmt_metric_row(f"**{dim}** — `v1_raw`", rep_v1["metrics"][key]))
        lines.append(_fmt_metric_row(f"**{dim}** — `v1_cc_offset`", rep_v1_cc["metrics"][key]))

    lines.extend(
        [
            "",
            "## 2. Tail-Strata Error & Bias Breakdown (Overall Band)",
            "",
            "| Stratum | N | `v0_raw` MAE / Bias | `v1_raw` MAE / Bias | `v1_cc_offset` MAE / Bias |",
            "|---|---:|---:|---:|---:|",
            "| Strict Low-Tail (`<= 5.0`) | 0 | *Reserved for future Active Sampling Low-Tail Supplement* | *Reserved* | *Reserved* |",
        ]
    )
    strata_rows = [
        ("low_tail_le_5_5", "Low-Tail (`<= 5.5`)"),
        ("mid_range_6_0_to_7_5", "Mid-Range (`6.0 - 7.5`)"),
        ("high_tail_ge_8_0", "High-Tail (`>= 8.0`)"),
        ("high_tail_ge_8_5", "Strict High-Tail (`>= 8.5`)"),
    ]
    for skey, slabel in strata_rows:
        s0 = rep_v0["metrics"]["overall"]["strata"][skey]
        s1 = rep_v1["metrics"]["overall"]["strata"][skey]
        sc = rep_v1_cc["metrics"]["overall"]["strata"][skey]
        lines.append(
            f"| {slabel} | {s0['n']} | {s0['mae']:.4f} / `{s0['mean_bias']:+.4f}` | "
            f"{s1['mae']:.4f} / `{s1['mean_bias']:+.4f}` | {sc['mae']:.4f} / `{sc['mean_bias']:+.4f}` |"
        )

    dq = paired_test["delta_qwk"]
    dm = paired_test["delta_macro_mae"]
    du = paired_test["delta_micro_mae"]
    lines.extend(
        [
            "",
            "## 3. Paired Clustered Bootstrap Significance Test (`v1_raw - v0_raw`, 1,000 Cluster Resamples)",
            "",
            "| Metric Difference (`v1_raw - v0_raw`) | Observed Delta | 95% Clustered Bootstrap CI | p-value (one-sided) | p-value (two-sided) |",
            "|---|---:|---:|---:|---:|",
            f"| **Delta Overall QWK** (`> 0` is better) | `{dq['observed']:+.4f}` | `[{dq['ci_95'][0]:+.4f}, {dq['ci_95'][1]:+.4f}]` | `{dq['p_one_sided']:.4f}` | `{dq['p_two_sided']:.4f}` |",
            f"| **Delta Overall Macro-MAE** (`< 0` is better) | `{dm['observed']:+.4f}` | `[{dm['ci_95'][0]:+.4f}, {dm['ci_95'][1]:+.4f}]` | `{dm['p_one_sided']:.4f}` | `{dm['p_two_sided']:.4f}` |",
            f"| **Delta Overall Micro-MAE** (`< 0` is better) | `{du['observed']:+.4f}` | `[{du['ci_95'][0]:+.4f}, {du['ci_95'][1]:+.4f}]` | `{du['p_one_sided']:.4f}` | `{du['p_two_sided']:.4f}` |",
        ]
    )

    tok_delta_pct = 100.0 * (t_v1["mean_tokens"] - t_v0["mean_tokens"]) / max(1.0, t_v0["mean_tokens"])
    lat_delta_pct = 100.0 * (t_v1["mean_latency_ms"] - t_v0["mean_latency_ms"]) / max(1.0, t_v0["mean_latency_ms"])
    lines.extend(
        [
            "",
            "## 4. Token & Latency Summary on Holdout (63 Essays)",
            "",
            "| Metric | `v0_raw` (15 Seed Anchors) | `v1_raw` (8 Stratified Anchors) | Delta (`v1 - v0`) |",
            "|---|---:|---:|---:|",
            f"| **Mean Latency (ms)** | `{t_v0['mean_latency_ms']}` | `{t_v1['mean_latency_ms']}` | `{lat_delta_pct:+.1f}%` |",
            f"| **P95 Latency (ms)** | `{t_v0['p95_latency_ms']}` | `{t_v1['p95_latency_ms']}` | `{t_v1['p95_latency_ms'] - t_v0['p95_latency_ms']:+d} ms` |",
            f"| **Mean Tokens / Essay** | `{t_v0['mean_tokens']:,.1f}` | `{t_v1['mean_tokens']:,.1f}` | `{tok_delta_pct:+.1f}%` |",
            f"| **Total Tokens (63 essays)** | `{t_v0['total_tokens']:,}` | `{t_v1['total_tokens']:,}` | `{t_v1['total_tokens'] - t_v0['total_tokens']:+,}` |",
        ]
    )

    md = "\n".join(lines) + "\n"
    (out_dir / "final_holdout_report.md").write_text(md, encoding="utf-8")
    (out_dir / "final_holdout_report.json").write_text(
        json.dumps(
            {
                "frozen_calibration": cal_payload,
                "v0_raw": rep_v0,
                "v1_raw": rep_v1,
                "v1_cc_offset": rep_v1_cc,
                "paired_bootstrap_test": paired_test,
                "telemetry": {"v0": t_v0, "v1": t_v1},
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return md


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Final One-Shot Holdout Evaluation (v0_raw vs v1_raw vs v1_cc_offset).")
    parser.add_argument("--seed-jsonl", type=Path, default=Path("artifacts/dataset_v1/seed.jsonl"))
    parser.add_argument("--holdout-jsonl", type=Path, default=Path("artifacts/dataset_v1/holdout.jsonl"))
    parser.add_argument(
        "--dev-v1-preds",
        type=Path,
        default=Path("artifacts/dataset_v1/candidate_v1/dev_live_predictions_v1.jsonl"),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/dataset_v1/final_holdout"))
    parser.add_argument("--rpm", type=int, default=10)
    parser.add_argument("--daily-budget", type=int, default=1000)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    md = asyncio.run(
        run_final_holdout_evaluation(
            seed_jsonl=args.seed_jsonl,
            holdout_jsonl=args.holdout_jsonl,
            dev_v1_preds=args.dev_v1_preds,
            out_dir=args.out_dir,
            rpm=args.rpm,
            daily_budget=args.daily_budget,
            resume=not args.no_resume,
        )
    )
    print(md)


if __name__ == "__main__":
    main()
