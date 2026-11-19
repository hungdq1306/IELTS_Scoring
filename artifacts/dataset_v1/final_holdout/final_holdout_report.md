# Final One-Shot Holdout Evaluation Report (`dataset_v1` — 63 Essays, 47 Clusters, 100% `max2_half`)

- **Holdout Set:** `63` essays across `47` independent prompt clusters (`100% max2_half`, zero prompt overlap `< 0.60` with `Seed` and `Dev`).
- **Frozen Dev Calibration (`dev_frozen_calibration.json`):** `cc_additive_offset = +0.1821` (learned strictly on 173 Dev essays; `0` parameters fitted on Holdout).
- **Benchmarks:** `QWK >= 0.70`, `|SMD| <= 0.15`, `SD Ratio in [0.67, 1.50]`, Clustered Bootstrap 95% CI (`1,000` cluster resamples).

## 1. Overall & Per-Criterion Psychometric Comparison (`v0_raw` vs `v1_raw` vs `v1_cc_offset`)

| Dimension / Variant | QWK [95% CI] | Micro-MAE [95% CI] | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **OVERALL** — `v0_raw` | `0.7847` [0.692, 0.845] (PASS) | 0.3968 [0.302, 0.500] | 0.4652 | -0.2857 | `-0.3490` (FAIL) | `1.059` (PASS) | 39.7% | 82.5% |
| **OVERALL** — `v1_raw` | `0.8712` [0.811, 0.910] (PASS) | 0.3413 [0.266, 0.417] | 0.3786 | -0.0079 | `-0.0087` (PASS) | `0.864` (PASS) | 39.7% | 92.1% |
| **OVERALL** — `v1_cc_offset` | `0.8712` [0.811, 0.910] (PASS) | 0.3413 [0.266, 0.417] | 0.3786 | -0.0079 | `-0.0087` (PASS) | `0.864` (PASS) | 39.7% | 92.1% |
| **TR** — `v0_raw` | `0.7038` [0.603, 0.783] (PASS) | 0.4444 [0.352, 0.550] | 0.4917 | -0.2857 | `-0.3924` (FAIL) | `1.092` (PASS) | 30.2% | 84.1% |
| **TR** — `v1_raw` | `0.7963` [0.715, 0.860] (PASS) | 0.3810 [0.288, 0.475] | 0.4142 | -0.0476 | `-0.0590` (PASS) | `0.890` (PASS) | 36.5% | 88.9% |
| **TR** — `v1_cc_offset` | `0.7963` [0.715, 0.860] (PASS) | 0.3810 [0.288, 0.475] | 0.4142 | -0.0476 | `-0.0590` (PASS) | `0.890` (PASS) | 36.5% | 88.9% |
| **CC** — `v0_raw` | `0.6985` [0.588, 0.787] (FAIL) | 0.5079 [0.398, 0.623] | 0.5552 | -0.4444 | `-0.5576` (FAIL) | `0.983` (PASS) | 30.2% | 73.0% |
| **CC** — `v1_raw` | `0.8133` [0.710, 0.888] (PASS) | 0.3571 [0.265, 0.455] | 0.4082 | -0.0714 | `-0.0841` (PASS) | `0.874` (PASS) | 42.9% | 88.9% |
| **CC** — `v1_cc_offset` | `0.8133` [0.710, 0.888] (PASS) | 0.3571 [0.265, 0.455] | 0.4082 | -0.0714 | `-0.0841` (PASS) | `0.874` (PASS) | 42.9% | 88.9% |
| **LR** — `v0_raw` | `0.8351` [0.750, 0.896] (PASS) | 0.3333 [0.234, 0.446] | 0.4154 | -0.2063 | `-0.2329` (FAIL) | `1.059` (PASS) | 49.2% | 87.3% |
| **LR** — `v1_raw` | `0.8727` [0.800, 0.921] (PASS) | 0.3254 [0.246, 0.410] | 0.3677 | +0.0556 | `+0.0575` (PASS) | `0.896` (PASS) | 47.6% | 88.9% |
| **LR** — `v1_cc_offset` | `0.8727` [0.800, 0.921] (PASS) | 0.3254 [0.246, 0.410] | 0.3677 | +0.0556 | `+0.0575` (PASS) | `0.896` (PASS) | 47.6% | 88.9% |
| **GRA** — `v0_raw` | `0.8492` [0.783, 0.894] (PASS) | 0.3651 [0.278, 0.461] | 0.4099 | -0.2698 | `-0.2805` (FAIL) | `1.061` (PASS) | 46.0% | 82.5% |
| **GRA** — `v1_raw` | `0.8804` [0.817, 0.921] (PASS) | 0.4048 [0.318, 0.500] | 0.4112 | +0.1032 | `+0.0932` (PASS) | `0.816` (PASS) | 33.3% | 88.9% |
| **GRA** — `v1_cc_offset` | `0.8804` [0.817, 0.921] (PASS) | 0.4048 [0.318, 0.500] | 0.4112 | +0.1032 | `+0.0932` (PASS) | `0.816` (PASS) | 33.3% | 88.9% |

## 2. Tail-Strata Error & Bias Breakdown (Overall Band)

| Stratum | N | `v0_raw` MAE / Bias | `v1_raw` MAE / Bias | `v1_cc_offset` MAE / Bias |
|---|---:|---:|---:|---:|
| Strict Low-Tail (`<= 5.0`) | 0 | *Reserved for future Active Sampling Low-Tail Supplement* | *Reserved* | *Reserved* |
| Low-Tail (`<= 5.5`) | 8 | 0.3750 / `+0.0000` | 0.3125 / `+0.1875` | 0.3125 / `+0.1875` |
| Mid-Range (`6.0 - 7.5`) | 45 | 0.3333 / `-0.2444` | 0.3111 / `-0.0667` | 0.3111 / `-0.0667` |
| High-Tail (`>= 8.0`) | 10 | 0.7000 / `-0.7000` | 0.5000 / `+0.1000` | 0.5000 / `+0.1000` |
| Strict High-Tail (`>= 8.5`) | 4 | 0.7500 / `-0.7500` | 0.5000 / `+0.0000` | 0.5000 / `+0.0000` |

## 3. Paired Clustered Bootstrap Significance Test (`v1_raw - v0_raw`, 1,000 Cluster Resamples)

| Metric Difference (`v1_raw - v0_raw`) | Observed Delta | 95% Clustered Bootstrap CI | p-value (one-sided) | p-value (two-sided) |
|---|---:|---:|---:|---:|
| **Delta Overall QWK** (`> 0` is better) | `+0.0865` | `[+0.0207, +0.1652]` | `0.0060` | `0.0120` |
| **Delta Overall Macro-MAE** (`< 0` is better) | `-0.0866` | `[-0.2281, +0.0339]` | `0.0880` | `0.1760` |
| **Delta Overall Micro-MAE** (`< 0` is better) | `-0.0556` | `[-0.1750, +0.0565]` | `0.1810` | `0.3620` |

## 4. Token & Latency Summary on Holdout (63 Essays)

| Metric | `v0_raw` (15 Seed Anchors) | `v1_raw` (8 Stratified Anchors) | Delta (`v1 - v0`) |
|---|---:|---:|---:|
| **Mean Latency (ms)** | `5702.5` | `5466.1` | `-4.1%` |
| **P95 Latency (ms)** | `7756` | `7400` | `-356 ms` |
| **Mean Tokens / Essay** | `8,324.4` | `5,511.7` | `-33.8%` |
| **Total Tokens (63 essays)** | `524,438` | `347,234` | `-177,204` |
