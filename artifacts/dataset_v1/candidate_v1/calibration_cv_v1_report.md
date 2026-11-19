# Zero-Cost Post-Hoc Calibration Benchmark (5-Fold GroupKFold by `prompt_cluster_id`)
- **Dataset:** Frozen `dataset_v1` Dev (`173` essays across `33` prompt clusters)
- **Cross-Validation:** Deterministic 5-Fold `GroupKFold` (zero prompt-cluster overlap between train & val folds)
- **Mean Learned Additive Offsets (`true - pred`):** `{'tr': 0.1092, 'cc': 0.1849, 'lr': 0.0128, 'gra': 0.0569}`
- **Mean Learned Ridge Params `(slope, intercept)`:** `{'tr': (0.687, 2.1467), 'cc': (0.6568, 2.401), 'lr': (0.7106, 1.8064), 'gra': (0.7297, 1.7219)}`

## 1. Overall Performance Comparison (Out-of-Fold)

| Method | Overall QWK [95% CI] | Micro-MAE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `raw_v0` | `0.8771` [0.829, 0.903] | 0.3497 | 0.3414 | -0.0896 | `-0.0926` (PASS) | `0.813` (PASS) | 41.0% | 89.0% |
| `criterion_offset` | `0.8708` [0.821, 0.903] | 0.3497 | 0.3380 | -0.0723 | `-0.0742` (PASS) | `0.805` (PASS) | 42.8% | 88.4% |
| `criterion_linear` | `0.8575` [0.792, 0.893] | 0.2977 | 0.3473 | +0.0318 | `+0.0395` (PASS) | `1.165` (PASS) | 47.4% | 93.1% |

## 2. Per-Criterion SMD & Mean Bias Comparison

| Method | TR Bias / SMD | CC Bias / SMD | LR Bias / SMD | GRA Bias / SMD |
|---|---|---|---|---|
| `raw_v0` | -0.107 / `-0.110` (PASS) | -0.182 / `-0.195` (FAIL) | -0.012 / `-0.012` (PASS) | -0.055 / `-0.051` (PASS) |
| `criterion_offset` | -0.107 / `-0.110` (PASS) | -0.026 / `-0.027` (PASS) | -0.012 / `-0.012` (PASS) | -0.055 / `-0.051` (PASS) |
| `criterion_linear` | +0.012 / `+0.014` (PASS) | +0.017 / `+0.023` (PASS) | +0.020 / `+0.024` (PASS) | +0.012 / `+0.013` (PASS) |
