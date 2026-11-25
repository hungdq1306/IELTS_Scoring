"""Prompt clustering, quarantine handling, and Tiered + Tail-Protected dataset splitting."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import re
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import yaml

from src.data.tiering import DroppedRecord, EssayRecord, load_and_tier_dataset

BAND_GRID = [4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0]
TIERS_ORDER = ("examiner_verified", "ai_augmented", "max2_half", "max3_half_only")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def compute_cosine_matrix(texts: list[str]) -> np.ndarray:
    """Compute deterministic L2-normalized TF-IDF (1,2)-gram cosine similarity matrix."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float64)
    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True, norm="l2")
    X = vec.fit_transform([normalize_text(t) for t in texts])
    sim = cosine_similarity(X).astype(np.float64)
    np.fill_diagonal(sim, 1.0)
    return sim


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def _assign_clusters_and_quarantine(
    records: list[EssayRecord],
    max_prompt_sim: float,
    near_dup_essay_sim: float,
) -> tuple[list[EssayRecord], list[dict[str, Any]], np.ndarray]:
    """Cluster prompts via cosine >= max_prompt_sim (plus near-dup essays), and quarantine examiner overlaps."""
    # Sort deterministically: examiner_verified first, then dual-rater by essay_id
    ordered = sorted(records, key=lambda r: (0 if r.quality_tier == "examiner_verified" else 1, r.essay_id))
    n = len(ordered)
    prompt_sim = compute_cosine_matrix([r.prompt for r in ordered])
    essay_sim = compute_cosine_matrix([r.essay for r in ordered])

    ex_indices = [i for i, r in enumerate(ordered) if r.quality_tier == "examiner_verified"]
    dr_indices = [i for i, r in enumerate(ordered) if r.quality_tier != "examiner_verified"]

    # Build connected components among dual-rater essays first
    uf_dr = _UnionFind(n)
    for idx_pos_i, i in enumerate(dr_indices):
        for j in dr_indices[idx_pos_i + 1 :]:
            if prompt_sim[i, j] >= max_prompt_sim or essay_sim[i, j] >= near_dup_essay_sim:
                uf_dr.union(i, j)

    # Identify any dual-rater cluster overlapping with any examiner_verified prompt/essay
    quarantined_roots: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i in dr_indices:
        for ex_i in ex_indices:
            p_s = float(prompt_sim[i, ex_i])
            e_s = float(essay_sim[i, ex_i])
            if p_s >= max_prompt_sim or e_s >= near_dup_essay_sim:
                quarantined_roots[uf_dr.find(i)].append(
                    {
                        "matched_examiner_id": ordered[ex_i].essay_id,
                        "prompt_cosine": round(p_s, 4),
                        "essay_cosine": round(e_s, 4),
                    }
                )

    quarantined: list[dict[str, Any]] = []
    kept_indices: list[int] = []
    for i in range(n):
        if i in ex_indices:
            kept_indices.append(i)
            continue
        root = uf_dr.find(i)
        if root in quarantined_roots:
            quarantined.append(
                {
                    "essay_id": ordered[i].essay_id,
                    "quality_tier": ordered[i].quality_tier,
                    "overall": ordered[i].overall,
                    "prompt": ordered[i].prompt,
                    "reason": "prompt_or_essay_overlap_with_examiner_seed",
                    "matches": quarantined_roots[root],
                }
            )
        else:
            kept_indices.append(i)

    kept = [ordered[i] for i in kept_indices]

    # Build final clusters on kept records (examiner + non-quarantined dual-rater)
    m = len(kept)
    kept_prompt_sim = compute_cosine_matrix([r.prompt for r in kept])
    kept_essay_sim = compute_cosine_matrix([r.essay for r in kept])
    uf_final = _UnionFind(m)
    for i in range(m):
        for j in range(i + 1, m):
            if kept_prompt_sim[i, j] >= max_prompt_sim or kept_essay_sim[i, j] >= near_dup_essay_sim:
                uf_final.union(i, j)

    comp_members: dict[int, list[int]] = defaultdict(list)
    for i in range(m):
        comp_members[uf_final.find(i)].append(i)

    # Deterministic human-readable cluster IDs
    ex_comps = []
    dr_comps = []
    for root, idxs in comp_members.items():
        first_id = min(kept[i].essay_id for i in idxs)
        is_ex = any(kept[i].quality_tier == "examiner_verified" for i in idxs)
        if is_ex:
            ex_comps.append((first_id, idxs))
        else:
            dr_comps.append((first_id, idxs))

    ex_comps.sort(key=lambda x: x[0])
    dr_comps.sort(key=lambda x: x[0])

    for rank, (_, idxs) in enumerate(ex_comps, start=1):
        cid = f"CL_EX_{rank:03d}"
        for i in idxs:
            kept[i].prompt_cluster_id = cid

    for rank, (_, idxs) in enumerate(dr_comps, start=1):
        cid = f"CL_DR_{rank:03d}"
        for i in idxs:
            kept[i].prompt_cluster_id = cid

    return kept, quarantined, kept_prompt_sim


def _optimize_holdout_clusters(
    pure_m2_clusters: dict[str, list[EssayRecord]],
    split_cfg: dict[str, Any],
    random_seed: int,
) -> tuple[set[str], set[str]]:
    """Deterministic multi-start simulated annealing to select pure max2_half clusters for Holdout."""
    cids = sorted(pure_m2_clusters.keys())
    total_pure = sum(len(pure_m2_clusters[c]) for c in cids)
    target_min = int(split_cfg["holdout_target_min"])
    target_max = int(split_cfg["holdout_target_max"])
    target_mid = (target_min + target_max) / 2.0
    low_max = float(split_cfg["low_tail_max_band"])
    high_min = float(split_cfg["high_tail_min_band"])
    bloated_bands = set(float(b) for b in split_cfg["mid_range_bloated_bands"])
    min_low = int(split_cfg["holdout_min_low_tail"])
    min_high = int(split_cfg["holdout_min_high_tail"])
    restarts = int(split_cfg.get("optimizer_restarts", 25))
    steps = int(split_cfg.get("optimizer_steps", 400))

    # If all pure max2_half clusters together do not exceed target_max, assigning all of them to Holdout
    # strictly maximizes Holdout sample size and protects 100% of available pure-tier tail essays.
    if total_pure <= target_max:
        return set(cids), set()

    # Precompute cluster feature vectors for fast scoring
    stats = {}
    for c in cids:
        items = pure_m2_clusters[c]
        stats[c] = (
            len(items),
            sum(1 for r in items if r.overall <= low_max),
            sum(1 for r in items if r.overall >= high_min),
            sum(1 for r in items if r.overall in bloated_bands),
        )

    def energy(selected: set[str]) -> float:
        n_tot = sum(stats[c][0] for c in selected)
        n_low = sum(stats[c][1] for c in selected)
        n_high = sum(stats[c][2] for c in selected)
        n_mid = sum(stats[c][3] for c in selected)

        # Heavily penalize falling outside [target_min, target_max] and missing tail minimums
        size_pen = 0.0
        if n_tot < target_min:
            size_pen = 50.0 * (target_min - n_tot)
        elif n_tot > target_max:
            size_pen = 50.0 * (n_tot - target_max)
        else:
            size_pen = 0.5 * abs(n_tot - target_mid)

        low_pen = 40.0 * max(0, min_low - n_low) - 4.0 * n_low
        high_pen = 40.0 * max(0, min_high - n_high) - 4.0 * n_high
        mid_ratio = n_mid / max(1, n_tot)
        mid_pen = 35.0 * max(0.0, mid_ratio - 0.40)
        return size_pen + low_pen + high_pen + mid_pen

    rng = random.Random(random_seed)
    best_sel: set[str] = set()
    best_e = float("inf")

    for _ in range(restarts):
        # Greedy tail-first warm start with randomized order
        shuffled = list(cids)
        rng.shuffle(shuffled)
        shuffled.sort(key=lambda c: (-(stats[c][1] + stats[c][2]), stats[c][3] / max(1, stats[c][0])))
        cur: set[str] = set()
        cur_n = 0
        for c in shuffled:
            if cur_n + stats[c][0] <= target_max:
                cur.add(c)
                cur_n += stats[c][0]
        cur_e = energy(cur)
        if cur_e < best_e:
            best_e, best_sel = cur_e, set(cur)

        temp = 10.0
        for _step in range(steps):
            cand = rng.choice(cids)
            if cand in cur:
                cur.remove(cand)
                new_e = energy(cur)
                if new_e < cur_e or rng.random() < math.exp((cur_e - new_e) / max(temp, 1e-6)):
                    cur_e = new_e
                else:
                    cur.add(cand)
            else:
                cur.add(cand)
                new_e = energy(cur)
                if new_e < cur_e or rng.random() < math.exp((cur_e - new_e) / max(temp, 1e-6)):
                    cur_e = new_e
                else:
                    cur.remove(cand)
            if cur_e < best_e:
                best_e, best_sel = cur_e, set(cur)
            temp *= 0.99

    return best_sel, set(cids) - best_sel


def _max_cross_sim(
    split_a: list[EssayRecord],
    split_b: list[EssayRecord],
    id_to_idx: dict[str, int],
    sim_matrix: np.ndarray,
) -> float:
    if not split_a or not split_b:
        return 0.0
    idx_a = [id_to_idx[r.essay_id] for r in split_a]
    idx_b = [id_to_idx[r.essay_id] for r in split_b]
    sub = sim_matrix[np.ix_(idx_a, idx_b)]
    return float(sub.max())


def _write_jsonl(path: Path, records: list[EssayRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: r.essay_id)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in ordered:
            fh.write(json.dumps(r.model_dump(), ensure_ascii=False) + "\n")


def _build_audit_report(
    *,
    seed_rows: list[EssayRecord],
    dev_rows: list[EssayRecord],
    holdout_rows: list[EssayRecord],
    dropped_records: list[DroppedRecord],
    quarantined: list[dict[str, Any]],
    tier_summary: dict[str, Any],
    cross_sim: dict[str, float],
    cluster_stats: dict[str, Any],
    config: dict[str, Any],
) -> str:
    all_rows = seed_rows + dev_rows + holdout_rows
    split_map = {"Seed": seed_rows, "Dev": dev_rows, "Holdout": holdout_rows, "Total": all_rows}

    lines: list[str] = [
        "# IELTS Writing Task 2 Dataset Audit Report (`dataset_v1`)",
        "",
        "## 1. Pipeline Configuration & Data Provenance",
        f"- **Random Seed:** `{config['random_seed']}` (fully deterministic)",
        f"- **Max Cross-Split Prompt Cosine Similarity Threshold:** `< {config['max_prompt_sim']:.2f}`",
        f"- **Near-Duplicate Essay Linkage Threshold:** `>= {config['near_dup_essay_sim']:.2f}`",
        f"- **Gold Label Aggregation:** `{config['gold_aggregation']}` (criterion midpoint aggregation; overall uses `{config['overall_policy']}`)",
        f"- **Raw Dual-Rater Pool:** `{tier_summary['dual_rater_raw']}` essays -> "
        f"`{tier_summary['max2_half']}` `max2_half`, `{tier_summary['max3_half_only']}` `max3_half_only`, "
        f"`{tier_summary['rejected']}` `rejected`, `{tier_summary['dropped_clean_or_outlier']}` dropped (artifacts/outliers).",
        f"- **Examiner-Verified Benchmark:** `{tier_summary['examiner_verified']}` essays (independently verified labels only).",
        f"- **Quarantined Prompt/Essay Overlaps with Seed:** `{len(quarantined)}` essays (logged in `quarantined_overlap.json`).",
        f"- **Total Retained Dataset:** **`{len(all_rows)}` essays** (`Seed: {len(seed_rows)}`, `Dev: {len(dev_rows)}`, `Holdout: {len(holdout_rows)}`).",
        "",
        "## 2. Score Distribution Across Splits (Overall Band 4.5–9.0)",
        "",
        "| Overall Band | Seed | Dev | Holdout | Total | Total (%) |",
        "|:---:|---:|---:|---:|---:|---:|",
    ]

    counts_by_split = {name: Counter(r.overall for r in rows) for name, rows in split_map.items()}
    for band in BAND_GRID:
        s_c = counts_by_split["Seed"][band]
        d_c = counts_by_split["Dev"][band]
        h_c = counts_by_split["Holdout"][band]
        t_c = counts_by_split["Total"][band]
        pct = (100.0 * t_c / len(all_rows)) if all_rows else 0.0
        lines.append(f"| **{band:.1f}** | {s_c} | {d_c} | {h_c} | **{t_c}** | {pct:.1f}% |")

    lines.append(
        f"| **Total** | **{len(seed_rows)}** | **{len(dev_rows)}** | **{len(holdout_rows)}** | **{len(all_rows)}** | **100.0%** |"
    )

    lines.extend(
        [
            "",
            "## 3. Quality Tier Breakdown Per Split",
            "",
            "| Quality Tier | Seed | Dev | Holdout | Total |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    tier_counts = {name: Counter(r.quality_tier for r in rows) for name, rows in split_map.items()}
    for tier in TIERS_ORDER:
        lines.append(
            f"| `{tier}` | {tier_counts['Seed'][tier]} | {tier_counts['Dev'][tier]} | "
            f"{tier_counts['Holdout'][tier]} | **{tier_counts['Total'][tier]}** |"
        )
    lines.append(
        f"| **Unique Prompt Clusters** | {len({r.prompt_cluster_id for r in seed_rows})} | "
        f"{len({r.prompt_cluster_id for r in dev_rows})} | {len({r.prompt_cluster_id for r in holdout_rows})} | "
        f"**{len({r.prompt_cluster_id for r in all_rows})}** |"
    )

    lines.extend(
        [
            "",
            "## 4. Cross-Split Maximum Prompt Cosine Similarity Matrix",
            "",
            "| Split Pair | Max Pairwise Cosine Similarity | Hard Threshold | Status |",
            "|---|:---:|:---:|:---:|",
            f"| `Seed` vs `Dev` | `{cross_sim['seed_vs_dev']:.4f}` | `< {config['max_prompt_sim']:.2f}` | PASS |",
            f"| `Seed` vs `Holdout` | `{cross_sim['seed_vs_holdout']:.4f}` | `< {config['max_prompt_sim']:.2f}` | PASS |",
            f"| `Dev` vs `Holdout` | `{cross_sim['dev_vs_holdout']:.4f}` | `< {config['max_prompt_sim']:.2f}` | PASS |",
            "",
            "## 5. Cluster Integrity & Holdout Purity Analysis",
            f"- **Pure `max2_half` Clusters Available (post-Seed):** `{cluster_stats['pure_m2_clusters_post_seed']}` clusters "
            f"(`{cluster_stats['pure_m2_essays_post_seed']}` essays).",
            f"- **Mixed-Tier Clusters Routed to `Dev`:** `{cluster_stats['mixed_clusters']}` clusters "
            f"(`{cluster_stats['mixed_essays']}` essays: `{cluster_stats['mixed_m2_essays']}` `max2_half` + "
            f"`{cluster_stats['mixed_m3_essays']}` `max3_half_only`) routed atomically to `Dev` to guarantee both "
            "`100% max2_half` purity in `Holdout` and Zero Prompt Overlap (`cosine < 0.60`).",
            f"- **Holdout Tail Coverage:** Low-tail (`<= 5.5`): `{sum(1 for r in holdout_rows if r.overall <= 5.5)}` essays "
            f"(`<= 5.0`: `{sum(1 for r in holdout_rows if r.overall <= 5.0)}`); "
            f"High-tail (`>= 8.0`): `{sum(1 for r in holdout_rows if r.overall >= 8.0)}` essays "
            f"(`>= 8.5`: `{sum(1 for r in holdout_rows if r.overall >= 8.5)}`).",
            "",
            "## 6. Data Gap Recommendation (Future Collection Rounds)",
        ]
    )

    strict_low_target = int(config["splits"]["balanced_low_tail_target"])
    total_low_50 = sum(1 for r in all_rows if r.overall <= 5.0)
    holdout_low_50 = sum(1 for r in holdout_rows if r.overall <= 5.0)
    seed_low_50 = sum(1 for r in seed_rows if r.overall <= 5.0)
    holdout_gap_50 = max(0, 10 - holdout_low_50)
    total_gap_50 = max(0, strict_low_target - holdout_low_50)
    holdout_size_gap = max(0, int(config["splits"]["holdout_target_min"]) - len(holdout_rows))

    lines.extend(
        [
            f"- **Current Low-Tail (`<= 5.0`) Inventory:** Total = `{total_low_50}` essays "
            f"(`Seed`: `{seed_low_50}`, `Dev`: `{total_low_50 - seed_low_50 - holdout_low_50}`, `Holdout`: `{holdout_low_50}`).",
            f"- **Exact Additional `<= 5.0` Essays Needed for `Holdout`:** Collect **`{holdout_gap_50}` additional** "
            f"prompt-disjoint `max2_half` (or examiner-verified) essays in Bands `4.5–5.0` to reach a minimum of `10` "
            f"strict low-tail essays in `Holdout` (or **`{total_gap_50}` additional** essays to reach the full balanced tail target of `{strict_low_target}`).",
            f"- **Holdout Pure-Cluster Expansion Note:** Because `{cluster_stats['mixed_m2_essays']}` `max2_half` essays "
            f"share prompts (`cosine >= 0.60`) with `max3_half_only` essays in large Writing9 clusters (routed to `Dev`), "
            f"`Holdout` currently contains `{len(holdout_rows)}` pure `max2_half` essays across "
            f"`{len({r.prompt_cluster_id for r in holdout_rows})}` unique prompt clusters. Collecting **`{holdout_size_gap}`+ additional** "
            f"prompt-disjoint `max2_half` essays on unseen prompts will bring `Holdout` into the `110–125` essay range while maintaining `100% max2_half` purity.",
            "",
            f"## 7. Dropped Records Summary (`dropped_records.json`)",
            f"- Total excluded/rejected records logged: `{len(dropped_records)}`",
        ]
    )
    drop_reasons = Counter(r.reason.split("(")[0].split(":")[0] for r in dropped_records)
    for reason, cnt in sorted(drop_reasons.items()):
        lines.append(f"  - `{reason}`: `{cnt}`")

    return "\n".join(lines) + "\n"


def run_split_pipeline(config_path: Path, root: Path | None = None, output_dir_override: Path | None = None) -> dict[str, Any]:
    """Execute end-to-end deterministic cleaning, tiering, clustering, splitting, and audit reporting."""
    repo_root = root or Path.cwd()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out_dir = output_dir_override or (repo_root / config["output_dir"])
    if (out_dir / "frozen_membership.json").exists():
        raise ValueError("Frozen dataset: use output_dir_override for a separate experiment")
    out_dir.mkdir(parents=True, exist_ok=True)

    retained, dropped, tier_summary = load_and_tier_dataset(config, root=repo_root)
    kept, quarantined, prompt_sim_matrix = _assign_clusters_and_quarantine(
        retained,
        max_prompt_sim=float(config["max_prompt_sim"]),
        near_dup_essay_sim=float(config["near_dup_essay_sim"]),
    )

    id_to_idx = {r.essay_id: i for i, r in enumerate(kept)}
    clusters: dict[str, list[EssayRecord]] = defaultdict(list)
    for r in kept:
        assert r.prompt_cluster_id is not None
        clusters[r.prompt_cluster_id].append(r)

    split_cfg = config["splits"]
    seed_extra_n = int(split_cfg["seed_extra_low_tail"])
    seed_low_max = float(split_cfg["seed_low_tail_max_band"])

    # 1. Assign all examiner_verified clusters to Seed (mandatory)
    seed_cids: set[str] = {
        cid for cid, items in clusters.items() if any(r.quality_tier in {"examiner_verified", "ai_augmented"} for r in items)
    }

    # 2. Classify remaining dual-rater clusters by tier purity
    pure_m2_clusters: dict[str, list[EssayRecord]] = {}
    mixed_clusters: dict[str, list[EssayRecord]] = {}
    pure_m3_clusters: dict[str, list[EssayRecord]] = {}

    for cid, items in clusters.items():
        if cid in seed_cids:
            continue
        tiers = {r.quality_tier for r in items}
        if tiers == {"max2_half"}:
            pure_m2_clusters[cid] = items
        elif tiers == {"max3_half_only"}:
            pure_m3_clusters[cid] = items
        else:
            mixed_clusters[cid] = items

    # 3. Low-tail anchoring for Seed: pick 2-3 small/singleton pure max2_half clusters in Bands 4.5-5.0
    low_anchor_candidates = [
        (len(items), min(r.overall for r in items), cid)
        for cid, items in pure_m2_clusters.items()
        if any(r.overall <= seed_low_max for r in items)
    ]
    low_anchor_candidates.sort()
    added_low_essays = 0
    for sz, _, cid in low_anchor_candidates:
        if added_low_essays >= seed_extra_n:
            break
        seed_cids.add(cid)
        del pure_m2_clusters[cid]
        added_low_essays += sz

    # 4. Optimize pure max2_half cluster selection for Holdout vs Dev
    holdout_cids, dev_pure_m2_cids = _optimize_holdout_clusters(
        pure_m2_clusters,
        split_cfg=split_cfg,
        random_seed=int(config["random_seed"]),
    )

    # 5. Route mixed-tier + pure max3_half_only + leftover pure max2_half to Dev
    dev_cids = set(mixed_clusters.keys()) | set(pure_m3_clusters.keys()) | dev_pure_m2_cids

    seed_rows = [r for cid in sorted(seed_cids) for r in clusters[cid]]
    dev_rows = [r for cid in sorted(dev_cids) for r in clusters[cid]]
    holdout_rows = [r for cid in sorted(holdout_cids) for r in clusters[cid]]

    # 6. Hard verification of cross-split cosine similarity < max_prompt_sim
    cross_sim = {
        "seed_vs_dev": _max_cross_sim(seed_rows, dev_rows, id_to_idx, prompt_sim_matrix),
        "seed_vs_holdout": _max_cross_sim(seed_rows, holdout_rows, id_to_idx, prompt_sim_matrix),
        "dev_vs_holdout": _max_cross_sim(dev_rows, holdout_rows, id_to_idx, prompt_sim_matrix),
    }
    max_sim_allowed = float(config["max_prompt_sim"])
    for pair_name, val in cross_sim.items():
        if val >= max_sim_allowed:
            raise RuntimeError(f"Hard constraint violated: {pair_name} cosine similarity {val:.4f} >= {max_sim_allowed}")

    # 7. Write output artifacts
    _write_jsonl(out_dir / "seed.jsonl", seed_rows)
    _write_jsonl(out_dir / "dev.jsonl", dev_rows)
    _write_jsonl(out_dir / "holdout.jsonl", holdout_rows)

    (out_dir / "dropped_records.json").write_text(
        json.dumps([d.model_dump() for d in dropped], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "quarantined_overlap.json").write_text(
        json.dumps(quarantined, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    cluster_stats = {
        "pure_m2_clusters_post_seed": len(pure_m2_clusters),
        "pure_m2_essays_post_seed": sum(len(v) for v in pure_m2_clusters.values()),
        "mixed_clusters": len(mixed_clusters),
        "mixed_essays": sum(len(v) for v in mixed_clusters.values()),
        "mixed_m2_essays": sum(1 for v in mixed_clusters.values() for r in v if r.quality_tier == "max2_half"),
        "mixed_m3_essays": sum(1 for v in mixed_clusters.values() for r in v if r.quality_tier == "max3_half_only"),
    }

    audit_md = _build_audit_report(
        seed_rows=seed_rows,
        dev_rows=dev_rows,
        holdout_rows=holdout_rows,
        dropped_records=dropped,
        quarantined=quarantined,
        tier_summary=tier_summary,
        cross_sim=cross_sim,
        cluster_stats=cluster_stats,
        config=config,
    )
    (out_dir / "audit_report.md").write_text(audit_md, encoding="utf-8")

    return {
        "seed_count": len(seed_rows),
        "dev_count": len(dev_rows),
        "holdout_count": len(holdout_rows),
        "quarantined_count": len(quarantined),
        "dropped_count": len(dropped),
        "cross_sim": cross_sim,
        "output_dir": str(out_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic IELTS Task 2 dataset splitting pipeline.")
    parser.add_argument("--config", type=Path, default=Path("configs/dataset_split.yaml"))
    args = parser.parse_args()
    result = run_split_pipeline(args.config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
