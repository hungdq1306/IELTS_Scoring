"""3-Way A/B Comparison Report (v0_raw vs v0_linear_calibrated vs v1_raw) + Conditional Calibration on Dev."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.eval.calibrate_v0 import run_calibration_cv
from src.eval.metrics import TARGET_KEYS, evaluate_predictions


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["essay_id"])
    return rows


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


def _fmt_row(label: str, m: dict[str, Any]) -> str:
    q_lo, q_hi = m["qwk_ci_95"]
    smd_flag = "PASS" if m["smd_pass"] else "FAIL"
    sdr_flag = "PASS" if m["sd_ratio_pass"] else "FAIL"
    sdr_s = f"`{m['sd_ratio']:.3f}` ({sdr_flag})" if m["sd_ratio"] is not None else "N/A"
    return (
        f"| {label} | `{m['qwk']:.4f}` [{q_lo:.3f}, {q_hi:.3f}] | {m['micro_mae']:.4f} | {m['macro_mae']:.4f} | "
        f"{m['mean_bias']:+.4f} | `{m['smd']:+.4f}` ({smd_flag}) | {sdr_s} | "
        f"{m['exact_agreement_pct']:.1f}% | {m['adjacent_agreement_pct']:.1f}% |"
    )


def generate_ab_report(
    v0_preds_path: Path = Path("artifacts/dataset_v1/baseline_v0/dev_live_predictions.jsonl"),
    v1_preds_path: Path = Path("artifacts/dataset_v1/candidate_v1/dev_live_predictions_v1.jsonl"),
    out_md: Path = Path("artifacts/dataset_v1/candidate_v1/ab_v0_vs_v1_dev.md"),
) -> str:
    v0_rows = _load_jsonl(v0_preds_path)
    v1_rows = _load_jsonl(v1_preds_path)
    assert [r["essay_id"] for r in v0_rows] == [r["essay_id"] for r in v1_rows], "v0 and v1 Dev essay_id mismatch!"

    v0_cal = run_calibration_cv(v0_preds_path, out_md=v0_preds_path.parent / "calibration_cv_report.md")
    v0_raw_rep = v0_cal["reports"]["raw_v0"]
    v0_lin_rep = v0_cal["reports"]["criterion_linear"]

    v1_pairs = [
        {
            "essay_id": r["essay_id"],
            "prompt_cluster_id": r["prompt_cluster_id"],
            "true": r["true"],
            "pred": r["pred"],
        }
        for r in v1_rows
    ]
    v1_raw_rep = evaluate_predictions(v1_pairs)

    t_v0 = _telemetry(v0_rows)
    t_v1 = _telemetry(v1_rows)

    lines: list[str] = [
        "# 3-Way A/B Benchmark Report: `v0_raw` vs `v0_linear_calibrated` vs `v1_raw` (Frozen Dev — 173 Essays, 33 Clusters)",
        "",
        "## 1. Overall & Per-Criterion Psychometric Comparison",
        "",
        "| Dimension / Variant | QWK [95% CI] | Micro-MAE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for key in TARGET_KEYS:
        dim = key.upper()
        lines.append(_fmt_row(f"**{dim}** — `v0_raw`", v0_raw_rep["metrics"][key]))
        lines.append(_fmt_row(f"**{dim}** — `v0_linear_cal`", v0_lin_rep["metrics"][key]))
        lines.append(_fmt_row(f"**{dim}** — `v1_raw`", v1_raw_rep["metrics"][key]))

    lines.extend(
        [
            "",
            "## 2. Tail-Strata Error & Bias Comparison (Overall Band)",
            "",
            "| Stratum | N | `v0_raw` MAE / Bias | `v0_linear_cal` MAE / Bias | `v1_raw` MAE / Bias |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    strata_meta = [
        ("low_tail_le_5_0", "Strict Low-Tail (`<= 5.0`)"),
        ("low_tail_le_5_5", "Low-Tail (`<= 5.5`)"),
        ("mid_range_6_0_to_7_5", "Mid-Range (`6.0 - 7.5`)"),
        ("high_tail_ge_8_0", "High-Tail (`>= 8.0`)"),
        ("high_tail_ge_8_5", "Strict High-Tail (`>= 8.5`)"),
    ]
    for skey, slabel in strata_meta:
        s0 = v0_raw_rep["metrics"]["overall"]["strata"][skey]
        sl = v0_lin_rep["metrics"]["overall"]["strata"][skey]
        s1 = v1_raw_rep["metrics"]["overall"]["strata"][skey]

        def _f(st: dict[str, Any]) -> str:
            if st["mae"] is None:
                return "N/A"
            return f"{st['mae']:.4f} / `{st['mean_bias']:+.4f}`"

        lines.append(f"| {slabel} | {s0['n']} | {_f(s0)} | {_f(sl)} | {_f(s1)} |")

    tok_delta_pct = 100.0 * (t_v1["mean_tokens"] - t_v0["mean_tokens"]) / max(1.0, t_v0["mean_tokens"])
    lat_delta_pct = 100.0 * (t_v1["mean_latency_ms"] - t_v0["mean_latency_ms"]) / max(1.0, t_v0["mean_latency_ms"])
    lines.extend(
        [
            "",
            "## 3. Token & Latency Comparison (`v0` vs `v1`)",
            "",
            "| Metric | `v0` (15 Seed Anchors) | `v1` (8 Stratified Anchors) | Delta (`v1 - v0`) |",
            "|---|---:|---:|---:|",
            f"| **Mean Latency (ms)** | `{t_v0['mean_latency_ms']}` | `{t_v1['mean_latency_ms']}` | `{lat_delta_pct:+.1f}%` |",
            f"| **P95 Latency (ms)** | `{t_v0['p95_latency_ms']}` | `{t_v1['p95_latency_ms']}` | `{t_v1['p95_latency_ms'] - t_v0['p95_latency_ms']:+d} ms` |",
            f"| **Mean Tokens / Essay** | `{t_v0['mean_tokens']:,.1f}` | `{t_v1['mean_tokens']:,.1f}` | `{tok_delta_pct:+.1f}%` |",
            f"| **Total Tokens (173 essays)** | `{t_v0['total_tokens']:,}` | `{t_v1['total_tokens']:,}` | `{t_v1['total_tokens'] - t_v0['total_tokens']:+,}` |",
        ]
    )

    # Conditional Zero-Cost Calibration Check if ANY dimension in v1_raw fails |SMD| <= 0.15
    failed_smd = [k.upper() for k in TARGET_KEYS if not v1_raw_rep["metrics"][k]["smd_pass"]]
    lines.extend(["", "## 4. Conditional Calibration Check on `v1_raw`"])
    if not failed_smd:
        lines.append("- **ALL 5 dimensions (`OVERALL`, `TR`, `CC`, `LR`, `GRA`) PASS `|SMD| <= 0.15` in `v1_raw`!** No post-hoc calibration required.")
    else:
        lines.append(f"- Dimensions failing `|SMD| <= 0.15` in `v1_raw`: `{', '.join(failed_smd)}`. Running 5-Fold GroupKFold (`prompt_cluster_id`) calibration check:")
        v1_cal = run_calibration_cv(v1_preds_path, out_md=out_md.parent / "calibration_cv_v1_report.md")
        lines.append(f"- **Mean Learned Additive Offsets (`true - pred`):** `{v1_cal['mean_offsets']}`")
        lines.append(f"- **Mean Learned Ridge Params `(slope, intercept)`:** `{v1_cal['mean_linear']}`")
        lines.extend(
            [
                "",
                "| `v1` Calibration Method | Overall QWK [95% CI] | Micro-MAE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for mname in ("raw_v0", "criterion_offset", "criterion_linear"):
            label = "v1_raw" if mname == "raw_v0" else f"v1_{mname}"
            lines.append(_fmt_row(f"`{label}`", v1_cal["reports"][mname]["metrics"]["overall"]))

        lines.extend(
            [
                "",
                "| `v1` Calibration Method | TR Bias / SMD | CC Bias / SMD | LR Bias / SMD | GRA Bias / SMD |",
                "|---|---|---|---|---|",
            ]
        )
        for mname in ("raw_v0", "criterion_offset", "criterion_linear"):
            label = "v1_raw" if mname == "raw_v0" else f"v1_{mname}"
            m = v1_cal["reports"][mname]["metrics"]
            cells = [
                f"{m[c]['mean_bias']:+.3f} / `{m[c]['smd']:+.3f}` ({'PASS' if m[c]['smd_pass'] else 'FAIL'})"
                for c in ("tr", "cc", "lr", "gra")
            ]
            lines.append(f"| `{label}` | " + " | ".join(cells) + " |")

    md = "\n".join(lines) + "\n"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    return md


if __name__ == "__main__":
    print(generate_ab_report())
