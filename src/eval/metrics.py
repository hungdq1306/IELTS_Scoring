"""Psychometric AES Evaluation Suite for IELTS Writing Task 2 (Williamson et al., 2012; Wang & von Davier; Yancey et al., 2023)."""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict

TARGET_KEYS = ("overall", "tr", "cc", "lr", "gra")
QWK_BENCHMARK = 0.70
SMD_BENCHMARK = 0.15
SD_RATIO_MIN = 0.67
SD_RATIO_MAX = 1.50
DEFAULT_BOOTSTRAP_ITERS = 1000
DEFAULT_BOOTSTRAP_SEED = 42

# Precomputed 19x19 quadratic weight matrix for classes 0..18 ([0.0, 9.0] in 0.5 steps)
_NUM_CLASSES = 19
_IDX = np.arange(_NUM_CLASSES, dtype=np.float64)
_QUAD_WEIGHTS = ((_IDX[:, None] - _IDX[None, :]) ** 2) / ((_NUM_CLASSES - 1) ** 2)


def to_band_class(score: float) -> int:
    """Map IELTS score in [0.0, 9.0] (0.5 steps) to integer class 0..18."""
    cls = int(round(float(score) * 2))
    return max(0, min(18, cls))


def _fast_qwk_classes(t_cls: np.ndarray, p_cls: np.ndarray) -> float:
    """Fast exact Quadratic Weighted Kappa over integer classes 0..18 (matches sklearn cohen_kappa_score)."""
    n = t_cls.shape[0]
    if n == 0:
        return 0.0
    if np.all(t_cls == t_cls[0]) and np.all(p_cls == p_cls[0]):
        return 1.0 if t_cls[0] == p_cls[0] else 0.0
    conf = np.zeros((_NUM_CLASSES, _NUM_CLASSES), dtype=np.float64)
    np.add.at(conf, (t_cls, p_cls), 1.0)
    hist_t = conf.sum(axis=1)
    hist_p = conf.sum(axis=0)
    expected = np.outer(hist_t, hist_p) / float(n)
    denom = float(np.sum(_QUAD_WEIGHTS * expected))
    if denom == 0.0:
        return 0.0
    num = float(np.sum(_QUAD_WEIGHTS * conf))
    return float(1.0 - (num / denom))


def quadratic_weighted_kappa(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Compute Quadratic Weighted Kappa (QWK) over 0.5-band integer classes 0..18."""
    if len(y_true) == 0:
        return 0.0
    t_cls = np.asarray([to_band_class(v) for v in y_true], dtype=np.int64)
    p_cls = np.asarray([to_band_class(v) for v in y_pred], dtype=np.int64)
    return _fast_qwk_classes(t_cls, p_cls)


def standardized_mean_difference(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Compute SMD = (mean(pred) - mean(true)) / pooled_std."""
    if len(y_true) < 2:
        return 0.0
    t = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(y_pred, dtype=np.float64)
    var_t = float(np.var(t, ddof=1))
    var_p = float(np.var(p, ddof=1))
    pooled_std = math.sqrt((var_t + var_p) / 2.0)
    if pooled_std == 0.0:
        return 0.0
    return float((np.mean(p) - np.mean(t)) / pooled_std)


def sd_ratio(y_true: Sequence[float], y_pred: Sequence[float]) -> float | None:
    """Compute SD Ratio (Wang & von Davier) = SD_Human / SD_AS (benchmark: [0.67, 1.50]).

    Values > 1.50 indicate score compression / central tendency bias in the automated scorer.
    """
    if len(y_true) < 2:
        return None
    t = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(y_pred, dtype=np.float64)
    sd_human = float(np.std(t, ddof=1))
    sd_as = float(np.std(p, ddof=1))
    if sd_as == 0.0:
        return None
    return float(sd_human / sd_as)


def macro_mae(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Compute Macro-MAE: unweighted arithmetic mean of per-band MAE across all present true bands."""
    by_band: dict[float, list[float]] = defaultdict(list)
    for t, p in zip(y_true, y_pred):
        by_band[float(t)].append(abs(float(p) - float(t)))
    if not by_band:
        return 0.0
    band_maes = [sum(errs) / len(errs) for errs in by_band.values()]
    return float(sum(band_maes) / len(band_maes))


def clustered_bootstrap_ci(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    cluster_ids: Sequence[str],
    *,
    n_boot: int = DEFAULT_BOOTSTRAP_ITERS,
    random_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Compute Clustered Bootstrap 95% CIs by resampling prompt_cluster_id with replacement."""
    n = len(y_true)
    if n == 0 or n_boot <= 0:
        return {
            "n_clusters": 0,
            "n_boot": n_boot,
            "qwk_ci_95": [0.0, 0.0],
            "micro_mae_ci_95": [0.0, 0.0],
        }

    t_arr = np.asarray(y_true, dtype=np.float64)
    p_arr = np.asarray(y_pred, dtype=np.float64)
    t_cls_arr = np.asarray([to_band_class(v) for v in y_true], dtype=np.int64)
    p_cls_arr = np.asarray([to_band_class(v) for v in y_pred], dtype=np.int64)

    by_cluster: dict[str, list[int]] = defaultdict(list)
    for idx, cid in enumerate(cluster_ids):
        by_cluster[str(cid)].append(idx)

    ordered_clusters = [np.asarray(by_cluster[k], dtype=np.int64) for k in sorted(by_cluster.keys())]
    k_clusters = len(ordered_clusters)
    rng = np.random.default_rng(random_seed)

    qwk_samples = np.empty(n_boot, dtype=np.float64)
    mae_samples = np.empty(n_boot, dtype=np.float64)

    for b in range(n_boot):
        drawn = rng.integers(0, k_clusters, size=k_clusters)
        idxs = np.concatenate([ordered_clusters[c] for c in drawn])
        qwk_samples[b] = _fast_qwk_classes(t_cls_arr[idxs], p_cls_arr[idxs])
        mae_samples[b] = float(np.mean(np.abs(p_arr[idxs] - t_arr[idxs])))

    q_lo, q_hi = np.percentile(qwk_samples, [2.5, 97.5])
    m_lo, m_hi = np.percentile(mae_samples, [2.5, 97.5])
    return {
        "n_clusters": k_clusters,
        "n_boot": n_boot,
        "qwk_ci_95": [round(float(q_lo), 4), round(float(q_hi), 4)],
        "micro_mae_ci_95": [round(float(m_lo), 4), round(float(m_hi), 4)],
    }


class StratumMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int
    mae: float | None = None
    mean_bias: float | None = None


class TargetMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    n: int
    qwk: float
    qwk_pass: bool
    qwk_ci_95: list[float]
    micro_mae: float
    micro_mae_ci_95: list[float]
    rmse: float
    macro_mae: float
    mean_bias: float
    smd: float
    smd_pass: bool
    sd_ratio: float | None = None
    sd_ratio_pass: bool
    exact_agreement_pct: float
    adjacent_agreement_pct: float
    bootstrap_clusters: int
    bootstrap_iters: int
    strata: dict[str, StratumMetrics]


def _stratum_stats(y_true: np.ndarray, y_pred: np.ndarray, mask: np.ndarray, min_n: int = 1) -> StratumMetrics:
    n = int(mask.sum())
    if n < min_n:
        return StratumMetrics(n=n, mae=None, mean_bias=None)
    diffs = y_pred[mask] - y_true[mask]
    return StratumMetrics(
        n=n,
        mae=round(float(np.mean(np.abs(diffs))), 4),
        mean_bias=round(float(np.mean(diffs)), 4),
    )


def compute_target_metrics(
    target: str,
    y_true: Sequence[float],
    y_pred: Sequence[float],
    *,
    cluster_ids: Sequence[str] | None = None,
    qwk_threshold: float = QWK_BENCHMARK,
    smd_threshold: float = SMD_BENCHMARK,
    sd_ratio_min: float = SD_RATIO_MIN,
    sd_ratio_max: float = SD_RATIO_MAX,
    n_boot: int = DEFAULT_BOOTSTRAP_ITERS,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> TargetMetrics:
    """Compute the full AES psychometric metric set for a single score dimension."""
    t = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(y_pred, dtype=np.float64)
    diffs = p - t
    abs_diffs = np.abs(diffs)

    qwk = quadratic_weighted_kappa(t, p)
    smd = standardized_mean_difference(t, p)
    sdr = sd_ratio(t, p)
    sdr_pass = (sdr is not None) and (sd_ratio_min <= sdr <= sd_ratio_max)

    cids = list(cluster_ids) if cluster_ids is not None else [f"item_{i}" for i in range(len(t))]
    boot = clustered_bootstrap_ci(t, p, cids, n_boot=n_boot, random_seed=bootstrap_seed)

    micro_mae_val = float(np.mean(abs_diffs)) if len(t) else 0.0
    rmse_val = float(math.sqrt(np.mean(diffs**2))) if len(t) else 0.0
    macro_mae_val = macro_mae(t, p)
    bias_val = float(np.mean(diffs)) if len(t) else 0.0
    exact_pct = float(100.0 * np.mean(abs_diffs == 0.0)) if len(t) else 0.0
    adj_pct = float(100.0 * np.mean(abs_diffs <= 0.5)) if len(t) else 0.0

    strata = {
        "low_tail_le_5_5": _stratum_stats(t, p, t <= 5.5, min_n=1),
        "low_tail_le_5_0": _stratum_stats(t, p, t <= 5.0, min_n=3),
        "mid_range_6_0_to_7_5": _stratum_stats(t, p, (t >= 6.0) & (t <= 7.5), min_n=1),
        "high_tail_ge_8_0": _stratum_stats(t, p, t >= 8.0, min_n=1),
        "high_tail_ge_8_5": _stratum_stats(t, p, t >= 8.5, min_n=1),
    }

    return TargetMetrics(
        target=target,
        n=len(t),
        qwk=round(qwk, 4),
        qwk_pass=qwk >= qwk_threshold,
        qwk_ci_95=boot["qwk_ci_95"],
        micro_mae=round(micro_mae_val, 4),
        micro_mae_ci_95=boot["micro_mae_ci_95"],
        rmse=round(rmse_val, 4),
        macro_mae=round(macro_mae_val, 4),
        mean_bias=round(bias_val, 4),
        smd=round(smd, 4),
        smd_pass=abs(smd) <= smd_threshold,
        sd_ratio=round(sdr, 4) if sdr is not None else None,
        sd_ratio_pass=sdr_pass,
        exact_agreement_pct=round(exact_pct, 2),
        adjacent_agreement_pct=round(adj_pct, 2),
        bootstrap_clusters=boot["n_clusters"],
        bootstrap_iters=boot["n_boot"],
        strata=strata,
    )


def evaluate_predictions(
    pairs: Sequence[dict[str, Any]],
    *,
    qwk_threshold: float = QWK_BENCHMARK,
    smd_threshold: float = SMD_BENCHMARK,
    sd_ratio_min: float = SD_RATIO_MIN,
    sd_ratio_max: float = SD_RATIO_MAX,
    n_boot: int = DEFAULT_BOOTSTRAP_ITERS,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Evaluate predictions across Overall and all 4 IELTS criteria.

    Each item in `pairs` must have keys `true` and `pred` (each with `overall`, `tr`, `cc`, `lr`, `gra`),
    and optionally `prompt_cluster_id` (falling back to `essay_id` for clustered bootstrap).
    """
    from copy import deepcopy
    from src.data.tiering import compute_ielts_overall
    pairs = deepcopy(pairs)
    for item in pairs:
        for side in ('true', 'pred'):
            scores = item[side]
            scores['overall'] = compute_ielts_overall(*(scores[c] for c in ('tr', 'cc', 'lr', 'gra')))
    cluster_ids = [
        str(item.get("prompt_cluster_id") or item.get("essay_id") or f"item_{i}")
        for i, item in enumerate(pairs)
    ]
    results: dict[str, Any] = {}
    for key in TARGET_KEYS:
        y_true = [float(item["true"][key]) for item in pairs]
        y_pred = [float(item["pred"][key]) for item in pairs]
        tm = compute_target_metrics(
            key,
            y_true,
            y_pred,
            cluster_ids=cluster_ids,
            qwk_threshold=qwk_threshold,
            smd_threshold=smd_threshold,
            sd_ratio_min=sd_ratio_min,
            sd_ratio_max=sd_ratio_max,
            n_boot=n_boot,
            bootstrap_seed=bootstrap_seed,
        )
        results[key] = tm.model_dump()
    return {
        "overall_policy": "half_band_threshold_0375_v1",
        "overall_reference": "computed_from_criteria",
        "n_essays": len(pairs),
        "n_clusters": len(set(cluster_ids)),
        "benchmarks": {
            "qwk_min": qwk_threshold,
            "smd_abs_max": smd_threshold,
            "sd_ratio_range": [sd_ratio_min, sd_ratio_max],
            "bootstrap_iters": n_boot,
        },
        "metrics": results,
    }


def render_metrics_markdown(report: dict[str, Any], title: str = "AES Evaluation Report") -> str:
    """Render structured JSON evaluation report as a GitHub-flavored Markdown report."""
    b = report["benchmarks"]
    sd_lo, sd_hi = b.get("sd_ratio_range", [SD_RATIO_MIN, SD_RATIO_MAX])
    lines = [
        f"# {title}",
        f"- **Overall policy:** `{report.get('overall_policy', 'unspecified')}` (computed from criteria; reported labels are separate)",
        f"- **Evaluated Essays:** `{report['n_essays']}` across `{report.get('n_clusters', report['n_essays'])}` prompt clusters",
        f"- **Benchmarks:** `QWK >= {b['qwk_min']:.2f}`, `|SMD| <= {b['smd_abs_max']:.2f}`, "
        f"`SD Ratio in [{sd_lo:.2f}, {sd_hi:.2f}]`, Clustered Bootstrap 95% CI (`{b.get('bootstrap_iters', DEFAULT_BOOTSTRAP_ITERS)}` iters)",
        "",
        "## Core Psychometric Metrics",
        "",
        "| Dimension | QWK [95% CI] | Micro-MAE [95% CI] | RMSE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adjacent (<=0.5, %) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in TARGET_KEYS:
        m = report["metrics"][key]
        qwk_flag = "PASS" if m["qwk_pass"] else "FAIL"
        smd_flag = "PASS" if m["smd_pass"] else "FAIL"
        sdr_val = f"`{m['sd_ratio']:.3f}`" if m["sd_ratio"] is not None else "N/A"
        sdr_flag = "PASS" if m["sd_ratio_pass"] else "FAIL"
        q_lo, q_hi = m["qwk_ci_95"]
        m_lo, m_hi = m["micro_mae_ci_95"]
        lines.append(
            f"| **{key.upper()}** | `{m['qwk']:.4f}` [{q_lo:.3f}, {q_hi:.3f}] ({qwk_flag}) | "
            f"{m['micro_mae']:.4f} [{m_lo:.3f}, {m_hi:.3f}] | {m['rmse']:.4f} | "
            f"{m['macro_mae']:.4f} | {m['mean_bias']:+.4f} | `{m['smd']:+.4f}` ({smd_flag}) | "
            f"{sdr_val} ({sdr_flag}) | {m['exact_agreement_pct']:.1f}% | {m['adjacent_agreement_pct']:.1f}% |"
        )

    lines.extend(
        [
            "",
            "## Tail-Strata Error & Bias Breakdown (Overall Band)",
            "",
            "| Stratum | N | Tail-MAE | Mean Bias (`pred - true`) |",
            "|---|---:|---:|---:|",
        ]
    )
    ov_strata = report["metrics"]["overall"]["strata"]
    labels = {
        "low_tail_le_5_5": "Low-Tail (`<= 5.5`)",
        "low_tail_le_5_0": "Strict Low-Tail (`<= 5.0`, reported if `n>=3`)",
        "mid_range_6_0_to_7_5": "Mid-Range (`6.0 - 7.5`)",
        "high_tail_ge_8_0": "High-Tail (`>= 8.0`)",
        "high_tail_ge_8_5": "Strict High-Tail (`>= 8.5`)",
    }
    for skey, label in labels.items():
        st = ov_strata[skey]
        mae_s = f"{st['mae']:.4f}" if st["mae"] is not None else "N/A"
        bias_s = f"{st['mean_bias']:+.4f}" if st["mean_bias"] is not None else "N/A"
        lines.append(f"| {label} | {st['n']} | {mae_s} | {bias_s} |")

    return "\n".join(lines) + "\n"


def export_metrics(report: dict[str, Any], json_path: Path, md_path: Path | None = None, title: str = "AES Evaluation Report") -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if md_path is not None:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_metrics_markdown(report, title=title), encoding="utf-8")
