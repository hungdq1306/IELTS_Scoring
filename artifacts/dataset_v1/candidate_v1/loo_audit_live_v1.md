# Examiner-Calibration 13-Fold LOO-CV Audit (live_v1)
- **Evaluated Essays:** `13` across `12` prompt clusters
- **Benchmarks:** `QWK >= 0.70`, `|SMD| <= 0.15`, `SD Ratio in [0.67, 1.50]`, Clustered Bootstrap 95% CI (`1000` iters)

## Core Psychometric Metrics

| Dimension | QWK [95% CI] | Micro-MAE [95% CI] | RMSE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adjacent (<=0.5, %) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **OVERALL** | `0.9727` [0.667, 0.993] (PASS) | 0.1923 [0.077, 0.321] | 0.3101 | 0.2083 | +0.1923 | `+0.1400` (PASS) | `0.984` (PASS) | 61.5% | 100.0% |
| **TR** | `0.9587` [0.727, 0.992] (PASS) | 0.2308 [0.083, 0.375] | 0.3922 | 0.2639 | +0.2308 | `+0.1637` (FAIL) | `0.982` (PASS) | 61.5% | 92.3% |
| **CC** | `0.9557` [0.667, 0.992] (PASS) | 0.2308 [0.083, 0.382] | 0.3922 | 0.2500 | +0.2308 | `+0.1695` (FAIL) | `1.024` (PASS) | 61.5% | 92.3% |
| **LR** | `0.9477` [0.000, 0.993] (PASS) | 0.2308 [0.042, 0.433] | 0.3922 | 0.2500 | +0.2308 | `+0.1845` (FAIL) | `1.053` (PASS) | 61.5% | 92.3% |
| **GRA** | `0.9109` [0.479, 1.000] (PASS) | 0.2308 [0.000, 0.625] | 0.5883 | 0.3000 | +0.2308 | `+0.1602` (FAIL) | `0.976` (PASS) | 76.9% | 92.3% |

## Tail-Strata Error & Bias Breakdown (Overall Band)

| Stratum | N | Tail-MAE | Mean Bias (`pred - true`) |
|---|---:|---:|---:|
| Low-Tail (`<= 5.5`) | 1 | 0.0000 | +0.0000 |
| Strict Low-Tail (`<= 5.0`, reported if `n>=3`) | 1 | N/A | N/A |
| Mid-Range (`6.0 - 7.5`) | 3 | 0.1667 | +0.1667 |
| High-Tail (`>= 8.0`) | 9 | 0.2222 | +0.2222 |
| Strict High-Tail (`>= 8.5`) | 6 | 0.0833 | +0.0833 |
