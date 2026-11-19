"""Zero-cost 5-Fold GroupKFold (by prompt_cluster_id) post-hoc calibration benchmark on Baseline v0 Dev logs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

from src.data.tiering import CRITERIA_KEYS, compute_ielts_overall, round_half
from src.eval.metrics import evaluate_predictions


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["essay_id"])
    return rows


def _clip_round_half(val: float) -> float:
    return max(0.0, min(9.0, round_half(val)))


def run_calibration_cv(
    dev_preds_path: Path = Path("artifacts/dataset_v1/baseline_v0/dev_live_predictions.jsonl"),
    out_md: Path = Path("artifacts/dataset_v1/baseline_v0/calibration_cv_report.md"),
    n_splits: int = 5,
) -> dict[str, Any]:
    rows = _load_jsonl(dev_preds_path)
    n = len(rows)
    groups = np.asarray([str(r["prompt_cluster_id"]) for r in rows])

    gkf = GroupKFold(n_splits=n_splits)

    oof_raw: list[dict[str, Any]] = []
    oof_offset: list[dict[str, Any]] = [None] * n  # type: ignore[list-item]
    oof_linear: list[dict[str, Any]] = [None] * n  # type: ignore[list-item]

    learned_offsets: list[dict[str, float]] = []
    learned_linear: list[dict[str, tuple[float, float]]] = []

    for r in rows:
        oof_raw.append(
            {
                "essay_id": r["essay_id"],
                "prompt_cluster_id": r["prompt_cluster_id"],
                "true": r["true"],
                "pred": r["pred"],
            }
        )

    for train_idx, val_idx in gkf.split(np.zeros(n), groups=groups):
        # Verify zero cluster leakage between train and val folds
        assert set(groups[train_idx]).isdisjoint(set(groups[val_idx]))

        fold_offsets: dict[str, float] = {}
        fold_models: dict[str, Ridge] = {}
        fold_lin_params: dict[str, tuple[float, float]] = {}

        for crit in CRITERIA_KEYS:
            y_tr = np.asarray([float(rows[i]["true"][crit]) for i in train_idx], dtype=np.float64)
            x_tr = np.asarray([float(rows[i]["pred"][crit]) for i in train_idx], dtype=np.float64)
            # Constant additive bias: mean(true - pred)
            fold_offsets[crit] = float(np.mean(y_tr - x_tr))

            # Ridge linear calibration per criterion
            model = Ridge(alpha=1.0)
            model.fit(x_tr.reshape(-1, 1), y_tr)
            fold_models[crit] = model
            fold_lin_params[crit] = (float(model.coef_[0]), float(model.intercept_))

        learned_offsets.append(fold_offsets)
        learned_linear.append(fold_lin_params)

        for i in val_idx:
            r = rows[i]
            p_off: dict[str, float] = {}
            p_lin: dict[str, float] = {}
            for crit in CRITERIA_KEYS:
                raw_v = float(r["pred"][crit])
                p_off[crit] = _clip_round_half(raw_v + fold_offsets[crit])
                lin_v = float(fold_models[crit].predict(np.asarray([[raw_v]]))[0])
                p_lin[crit] = _clip_round_half(lin_v)

            p_off["overall"] = compute_ielts_overall(p_off["tr"], p_off["cc"], p_off["lr"], p_off["gra"])
            p_lin["overall"] = compute_ielts_overall(p_lin["tr"], p_lin["cc"], p_lin["lr"], p_lin["gra"])

            oof_offset[i] = {
                "essay_id": r["essay_id"],
                "prompt_cluster_id": r["prompt_cluster_id"],
                "true": r["true"],
                "pred": p_off,
            }
            oof_linear[i] = {
                "essay_id": r["essay_id"],
                "prompt_cluster_id": r["prompt_cluster_id"],
                "true": r["true"],
                "pred": p_lin,
            }

    reports = {
        "raw_v0": evaluate_predictions(oof_raw),
        "criterion_offset": evaluate_predictions(oof_offset),
        "criterion_linear": evaluate_predictions(oof_linear),
    }

    mean_offsets = {
        crit: round(float(np.mean([f[crit] for f in learned_offsets])), 4) for crit in CRITERIA_KEYS
    }
    mean_linear = {
        crit: (
            round(float(np.mean([f[crit][0] for f in learned_linear])), 4),
            round(float(np.mean([f[crit][1] for f in learned_linear])), 4),
        )
        for crit in CRITERIA_KEYS
    }

    lines: list[str] = [
        "# Zero-Cost Post-Hoc Calibration Benchmark (5-Fold GroupKFold by `prompt_cluster_id`)",
        f"- **Dataset:** Frozen `dataset_v1` Dev (`{n}` essays across `{len(set(groups))}` prompt clusters)",
        "- **Cross-Validation:** Deterministic 5-Fold `GroupKFold` (zero prompt-cluster overlap between train & val folds)",
        f"- **Mean Learned Additive Offsets (`true - pred`):** `{mean_offsets}`",
        f"- **Mean Learned Ridge Params `(slope, intercept)`:** `{mean_linear}`",
        "",
        "## 1. Overall Performance Comparison (Out-of-Fold)",
        "",
        "| Method | Overall QWK [95% CI] | Micro-MAE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("raw_v0", "criterion_offset", "criterion_linear"):
        ov = reports[name]["metrics"]["overall"]
        q_lo, q_hi = ov["qwk_ci_95"]
        smd_flag = "PASS" if ov["smd_pass"] else "FAIL"
        sdr_flag = "PASS" if ov["sd_ratio_pass"] else "FAIL"
        lines.append(
            f"| `{name}` | `{ov['qwk']:.4f}` [{q_lo:.3f}, {q_hi:.3f}] | {ov['micro_mae']:.4f} | {ov['macro_mae']:.4f} | "
            f"{ov['mean_bias']:+.4f} | `{ov['smd']:+.4f}` ({smd_flag}) | `{ov['sd_ratio']:.3f}` ({sdr_flag}) | "
            f"{ov['exact_agreement_pct']:.1f}% | {ov['adjacent_agreement_pct']:.1f}% |"
        )

    lines.extend(
        [
            "",
            "## 2. Per-Criterion SMD & Mean Bias Comparison",
            "",
            "| Method | TR Bias / SMD | CC Bias / SMD | LR Bias / SMD | GRA Bias / SMD |",
            "|---|---|---|---|---|",
        ]
    )
    for name in ("raw_v0", "criterion_offset", "criterion_linear"):
        m = reports[name]["metrics"]
        cells = []
        for crit in CRITERIA_KEYS:
            c = m[crit]
            flag = "PASS" if c["smd_pass"] else "FAIL"
            cells.append(f"{c['mean_bias']:+.3f} / `{c['smd']:+.3f}` ({flag})")
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")

    md = "\n".join(lines) + "\n"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    return {"reports": reports, "mean_offsets": mean_offsets, "mean_linear": mean_linear, "markdown": md}


if __name__ == "__main__":
    res = run_calibration_cv()
    print(res["markdown"])
