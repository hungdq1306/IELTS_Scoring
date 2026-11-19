# IELTS Writing Task 2 Dataset Audit Report (`dataset_v1`)

## 1. Pipeline Configuration & Data Provenance
- **Random Seed:** `42` (fully deterministic)
- **Max Cross-Split Prompt Cosine Similarity Threshold:** `< 0.60`
- **Near-Duplicate Essay Linkage Threshold:** `>= 0.85`
- **Gold Label Aggregation:** `midpoint_round_half_up` (official IELTS `ROUND_HALF_UP` to `0.5` increments)
- **Raw Dual-Rater Pool:** `862` essays -> `167` `max2_half`, `71` `max3_half_only`, `619` `rejected`, `5` dropped (artifacts/outliers).
- **Examiner-Verified Benchmark:** `13` essays (7 detailed lecturer essays 5.0–8.0 + 6 verified high-band essays 8.5–9.0).
- **Quarantined Prompt/Essay Overlaps with Seed:** `0` essays (logged in `quarantined_overlap.json`).
- **Total Retained Dataset:** **`251` essays** (`Seed: 15`, `Dev: 173`, `Holdout: 63`).

## 2. Score Distribution Across Splits (Overall Band 4.5–9.0)

| Overall Band | Seed | Dev | Holdout | Total | Total (%) |
|:---:|---:|---:|---:|---:|---:|
| **4.5** | 0 | 8 | 0 | **8** | 3.2% |
| **5.0** | 3 | 6 | 0 | **9** | 3.6% |
| **5.5** | 0 | 20 | 8 | **28** | 11.2% |
| **6.0** | 1 | 23 | 10 | **34** | 13.5% |
| **6.5** | 2 | 52 | 16 | **70** | 27.9% |
| **7.0** | 0 | 36 | 15 | **51** | 20.3% |
| **7.5** | 0 | 18 | 4 | **22** | 8.8% |
| **8.0** | 3 | 7 | 6 | **16** | 6.4% |
| **8.5** | 1 | 2 | 4 | **7** | 2.8% |
| **9.0** | 5 | 1 | 0 | **6** | 2.4% |
| **Total** | **15** | **173** | **63** | **251** | **100.0%** |

## 3. Quality Tier Breakdown Per Split

| Quality Tier | Seed | Dev | Holdout | Total |
|---|---:|---:|---:|---:|
| `examiner_verified` | 13 | 0 | 0 | **13** |
| `max2_half` | 2 | 102 | 63 | **167** |
| `max3_half_only` | 0 | 71 | 0 | **71** |
| **Unique Prompt Clusters** | 14 | 33 | 47 | **94** |

## 4. Cross-Split Maximum Prompt Cosine Similarity Matrix

| Split Pair | Max Pairwise Cosine Similarity | Hard Threshold | Status |
|---|:---:|:---:|:---:|
| `Seed` vs `Dev` | `0.1470` | `< 0.60` | PASS |
| `Seed` vs `Holdout` | `0.5861` | `< 0.60` | PASS |
| `Dev` vs `Holdout` | `0.5938` | `< 0.60` | PASS |

## 5. Cluster Integrity & Holdout Purity Analysis
- **Pure `max2_half` Clusters Available (post-Seed):** `47` clusters (`63` essays).
- **Mixed-Tier Clusters Routed to `Dev`:** `22` clusters (`160` essays: `102` `max2_half` + `58` `max3_half_only`) routed atomically to `Dev` to guarantee both `100% max2_half` purity in `Holdout` and Zero Prompt Overlap (`cosine < 0.60`).
- **Holdout Tail Coverage:** Low-tail (`<= 5.5`): `8` essays (`<= 5.0`: `0`); High-tail (`>= 8.0`): `10` essays (`>= 8.5`: `4`).

## 6. Data Gap Recommendation (Future Collection Rounds)
- **Current Low-Tail (`<= 5.0`) Inventory:** Total = `17` essays (`Seed`: `3`, `Dev`: `14`, `Holdout`: `0`).
- **Exact Additional `<= 5.0` Essays Needed for `Holdout`:** Collect **`10` additional** prompt-disjoint `max2_half` (or examiner-verified) essays in Bands `4.5–5.0` to reach a minimum of `10` strict low-tail essays in `Holdout` (or **`15` additional** essays to reach the full balanced tail target of `15`).
- **Holdout Pure-Cluster Expansion Note:** Because `102` `max2_half` essays share prompts (`cosine >= 0.60`) with `max3_half_only` essays in large Writing9 clusters (routed to `Dev`), `Holdout` currently contains `63` pure `max2_half` essays across `47` unique prompt clusters. Collecting **`47`+ additional** prompt-disjoint `max2_half` essays on unseen prompts will bring `Holdout` into the `110–125` essay range while maintaining `100% max2_half` purity.

## 7. Dropped Records Summary (`dropped_records.json`)
- Total excluded/rejected records logged: `624`
  - `high_criterion_spread`: `4`
  - `scraped_artifact_in_essay`: `1`
  - `tier_rejected`: `619`
