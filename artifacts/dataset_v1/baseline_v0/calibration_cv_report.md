# Zero-Cost Post-Hoc Calibration Benchmark (5-Fold GroupKFold by `prompt_cluster_id`)
- **Dataset:** Frozen `dataset_v1` Dev (`173` essays across `33` prompt clusters)
- **Cross-Validation:** Deterministic 5-Fold `GroupKFold` (zero prompt-cluster overlap between train & val folds)
- **Mean Learned Additive Offsets (`true - pred`):** `{'tr': 0.303, 'cc': 0.4432, 'lr': 0.2621, 'gra': 0.3869}`
- **Mean Learned Ridge Params `(slope, intercept)`:** `{'tr': (0.9296, 0.7489), 'cc': (0.8123, 1.6061), 'lr': (0.8502, 1.1528), 'gra': (0.847, 1.2786)}`

## 1. Overall Performance Comparison (Out-of-Fold)

| Method | Overall QWK [95% CI] | Micro-MAE | Macro-MAE | Mean Bias | SMD | SD Ratio | Exact (%) | Adj <= 0.5 (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `raw_v0` | `0.8443` [0.762, 0.885] | 0.3844 | 0.4668 | -0.3324 | `-0.3786` (FAIL) | `0.967` (PASS) | 35.3% | 88.4% |
| `criterion_offset` | `0.8945` [0.838, 0.912] | 0.2803 | 0.3124 | +0.0838 | `+0.0952` (PASS) | `0.963` (PASS) | 48.5% | 95.4% |
| `criterion_linear` | `0.8818` [0.824, 0.907] | 0.2630 | 0.3794 | +0.0318 | `+0.0392` (PASS) | `1.144` (PASS) | 52.0% | 95.4% |

## 2. Per-Criterion SMD & Mean Bias Comparison

| Method | TR Bias / SMD | CC Bias / SMD | LR Bias / SMD | GRA Bias / SMD |
|---|---|---|---|---|
| `raw_v0` | -0.303 / `-0.354` (FAIL) | -0.442 / `-0.534` (FAIL) | -0.263 / `-0.288` (FAIL) | -0.387 / `-0.386` (FAIL) |
| `criterion_offset` | +0.197 / `+0.229` (FAIL) | +0.058 / `+0.070` (PASS) | -0.009 / `-0.009` (PASS) | +0.113 / `+0.112` (PASS) |
| `criterion_linear` | +0.087 / `+0.106` (PASS) | +0.064 / `+0.081` (PASS) | -0.017 / `-0.021` (PASS) | +0.035 / `+0.037` (PASS) |
