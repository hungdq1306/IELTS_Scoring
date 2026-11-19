# Examiner-Calibration 13-Fold LOO-CV Audit (live_v0)
- **Evaluated Essays:** `13` across `12` prompt clusters
- **Benchmarks:** `QWK >= 0.70`, `|SMD| <= 0.15`, `SD Ratio in [0.67, 1.50]`, Clustered Bootstrap 95% CI (`1000` iters)

## Core Psychometric Metrics

| Dimension | QWK [95% CI] | Micro-MAE [95% CI] | RMSE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adjacent (<=0.5, %) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **OVERALL** | `0.7955` [0.218, 0.917] (PASS) | 0.5769 [0.300, 0.875] | 0.7721 | 0.3500 | -0.5769 | `-0.4878` (FAIL) | `1.403` (PASS) | 38.5% | 53.9% |
| **TR** | `0.7963` [0.227, 0.924] (PASS) | 0.6154 [0.375, 0.846] | 0.7845 | 0.5764 | -0.4615 | `-0.3743` (FAIL) | `1.338` (PASS) | 30.8% | 53.9% |
| **CC** | `0.7010` [0.198, 0.873] (PASS) | 0.7692 [0.462, 1.042] | 0.9405 | 0.5611 | -0.6154 | `-0.5206` (FAIL) | `1.454` (PASS) | 23.1% | 38.5% |
| **LR** | `0.8145` [0.178, 0.940] (PASS) | 0.5385 [0.321, 0.769] | 0.6794 | 0.3958 | -0.3846 | `-0.3416` (FAIL) | `1.358` (PASS) | 23.1% | 76.9% |
| **GRA** | `0.8054` [0.296, 0.893] (PASS) | 0.6538 [0.417, 0.885] | 0.7966 | 0.4500 | -0.5769 | `-0.4580` (FAIL) | `1.329` (PASS) | 30.8% | 38.5% |

## Tail-Strata Error & Bias Breakdown (Overall Band)

| Stratum | N | Tail-MAE | Mean Bias (`pred - true`) |
|---|---:|---:|---:|
| Low-Tail (`<= 5.5`) | 1 | 0.0000 | +0.0000 |
| Strict Low-Tail (`<= 5.0`, reported if `n>=3`) | 1 | N/A | N/A |
| Mid-Range (`6.0 - 7.5`) | 3 | 0.0000 | +0.0000 |
| High-Tail (`>= 8.0`) | 9 | 0.8333 | -0.8333 |
| Strict High-Tail (`>= 8.5`) | 6 | 1.0000 | -1.0000 |
