"""Automated integrity & determinism tests for the IELTS Writing Task 2 dataset_v1 pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.data.splitter import compute_cosine_matrix, normalize_text, run_split_pipeline
from src.data.tiering import EssayRecord
from src.eval.loo_audit import DeterministicMockScorer, run_loo_audit
from src.eval.metrics import (
    clustered_bootstrap_ci,
    quadratic_weighted_kappa,
    sd_ratio,
)
from sklearn.metrics import cohen_kappa_score

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "dataset_split.yaml"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dataset_v1"


def _load_jsonl(path: Path) -> list[EssayRecord]:
    assert path.exists(), f"Missing dataset artifact: {path}"
    rows: list[EssayRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(EssayRecord.model_validate_json(line))
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def splits() -> dict[str, list[EssayRecord]]:
    if not (ARTIFACT_DIR / "seed.jsonl").exists():
        run_split_pipeline(CONFIG_PATH, root=REPO_ROOT)
    return {
        "seed": _load_jsonl(ARTIFACT_DIR / "seed.jsonl"),
        "dev": _load_jsonl(ARTIFACT_DIR / "dev.jsonl"),
        "holdout": _load_jsonl(ARTIFACT_DIR / "holdout.jsonl"),
    }


def test_zero_essay_id_and_text_overlap(splits: dict[str, list[EssayRecord]]) -> None:
    """1. Zero essay_id or exact/near-duplicate essay text overlap across Seed, Dev, and Holdout."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    near_thresh = float(cfg["near_dup_essay_sim"])

    id_sets = {k: {r.essay_id for r in v} for k, v in splits.items()}
    assert id_sets["seed"].isdisjoint(id_sets["dev"])
    assert id_sets["seed"].isdisjoint(id_sets["holdout"])
    assert id_sets["dev"].isdisjoint(id_sets["holdout"])

    text_hashes = {k: {hashlib.sha256(normalize_text(r.essay).encode("utf-8")).hexdigest() for r in v} for k, v in splits.items()}
    assert text_hashes["seed"].isdisjoint(text_hashes["dev"])
    assert text_hashes["seed"].isdisjoint(text_hashes["holdout"])
    assert text_hashes["dev"].isdisjoint(text_hashes["holdout"])

    # Near-duplicate cross-split essay check
    all_rows = [(name, r) for name in ("seed", "dev", "holdout") for r in splits[name]]
    sim = compute_cosine_matrix([r.essay for _, r in all_rows])
    for i in range(len(all_rows)):
        for j in range(i + 1, len(all_rows)):
            if all_rows[i][0] != all_rows[j][0]:
                assert sim[i, j] < near_thresh, (
                    f"Cross-split near-duplicate essay detected: "
                    f"{all_rows[i][1].essay_id} ({all_rows[i][0]}) vs {all_rows[j][1].essay_id} ({all_rows[j][0]}) "
                    f"cos={sim[i, j]:.4f}"
                )


def test_zero_prompt_cluster_overlap(splits: dict[str, list[EssayRecord]]) -> None:
    """2. Zero prompt_cluster_id overlap across splits."""
    c_sets = {k: {r.prompt_cluster_id for r in v} for k, v in splits.items()}
    for name, cset in c_sets.items():
        assert None not in cset, f"Unassigned prompt_cluster_id in {name}"
    assert c_sets["seed"].isdisjoint(c_sets["dev"])
    assert c_sets["seed"].isdisjoint(c_sets["holdout"])
    assert c_sets["dev"].isdisjoint(c_sets["holdout"])


def test_max_cross_split_prompt_cosine_below_threshold(splits: dict[str, list[EssayRecord]]) -> None:
    """3. Maximum cross-split prompt cosine similarity < 0.60."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    max_allowed = float(cfg["max_prompt_sim"])

    all_rows = [(name, r) for name in ("seed", "dev", "holdout") for r in splits[name]]
    sim = compute_cosine_matrix([r.prompt for _, r in all_rows])
    indices = {
        name: [idx for idx, (sp, _) in enumerate(all_rows) if sp == name]
        for name in ("seed", "dev", "holdout")
    }
    for a, b in (("seed", "dev"), ("seed", "holdout"), ("dev", "holdout")):
        sub = sim[np.ix_(indices[a], indices[b])]
        max_sim = float(sub.max()) if sub.size else 0.0
        assert max_sim < max_allowed, f"Cross-split prompt similarity violated for {a} vs {b}: {max_sim:.4f} >= {max_allowed}"


def test_holdout_tier_purity(splits: dict[str, list[EssayRecord]]) -> None:
    """4. Holdout contains 100% max2_half (0 max3_half_only, 0 examiner_verified)."""
    holdout = splits["holdout"]
    assert len(holdout) > 0
    tiers = {r.quality_tier for r in holdout}
    assert tiers == {"max2_half"}, f"Holdout must be 100% max2_half, got {tiers}"


def test_seed_contains_all_13_examiner_verified(splits: dict[str, list[EssayRecord]]) -> None:
    """5. Seed contains all 13/13 examiner_verified essays (and 0 in Dev/Holdout)."""
    seed_ex = [r for r in splits["seed"] if r.quality_tier == "examiner_verified"]
    dev_ex = [r for r in splits["dev"] if r.quality_tier == "examiner_verified"]
    hold_ex = [r for r in splits["holdout"] if r.quality_tier == "examiner_verified"]
    assert len(seed_ex) == 13
    assert len(dev_ex) == 0
    assert len(hold_ex) == 0


def test_bit_for_bit_determinism(tmp_path: Path) -> None:
    """6. Bit-for-bit determinism across repeated runs with the same random_seed."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    run_split_pipeline(CONFIG_PATH, root=REPO_ROOT, output_dir_override=out1)
    run_split_pipeline(CONFIG_PATH, root=REPO_ROOT, output_dir_override=out2)

    for fname in ("seed.jsonl", "dev.jsonl", "holdout.jsonl", "dropped_records.json", "quarantined_overlap.json", "audit_report.md"):
        assert _sha256(out1 / fname) == _sha256(out2 / fname), f"Non-deterministic output detected in {fname}"


def test_loo_cv_dry_run_zero_leakage(tmp_path: Path) -> None:
    """Verify 13-fold LOO-CV runs cleanly with zero target leakage and exports valid metrics."""
    report = run_loo_audit(
        seed_jsonl=ARTIFACT_DIR / "seed.jsonl",
        scorer=DeterministicMockScorer(random_seed=42),
        out_dir=tmp_path,
        mode_label="test_dry_run",
    )
    assert report["n_folds"] == 13
    assert report["n_essays"] == 13
    assert len(report["folds"]) == 13
    assert all(f["fewshot_pool_size"] == 12 for f in report["folds"])
    assert (tmp_path / "loo_audit_test_dry_run.json").exists()
    assert (tmp_path / "loo_audit_test_dry_run.md").exists()
    ov = report["metrics"]["overall"]
    assert "sd_ratio" in ov and "sd_ratio_pass" in ov
    assert len(ov["qwk_ci_95"]) == 2 and ov["qwk_ci_95"][0] <= ov["qwk_ci_95"][1]
    assert ov["bootstrap_iters"] == 1000


def test_sd_ratio_and_clustered_bootstrap_metrics() -> None:
    """Verify SD Ratio (Wang & von Davier), fast QWK vs sklearn, and Clustered Bootstrap 95% CI."""
    y_true = [4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0]
    y_compressed = [6.0, 6.0, 6.5, 6.5, 6.5, 7.0, 7.0, 7.0, 7.5, 7.5]
    cids = ["C1", "C1", "C2", "C2", "C3", "C3", "C4", "C4", "C5", "C5"]

    # 1. Fast QWK matches sklearn cohen_kappa_score exactly
    sk_qwk = cohen_kappa_score(
        [int(round(v * 2)) for v in y_true],
        [int(round(v * 2)) for v in y_compressed],
        labels=list(range(19)),
        weights="quadratic",
    )
    assert abs(quadratic_weighted_kappa(y_true, y_compressed) - sk_qwk) < 1e-12

    # 2. SD Ratio > 1.50 flags central-tendency compression
    sdr = sd_ratio(y_true, y_compressed)
    assert sdr is not None and sdr > 1.50

    # 3. Clustered Bootstrap 95% CI is deterministic and resamples by prompt_cluster_id
    b1 = clustered_bootstrap_ci(y_true, y_compressed, cids, n_boot=1000, random_seed=42)
    b2 = clustered_bootstrap_ci(y_true, y_compressed, cids, n_boot=1000, random_seed=42)
    assert b1 == b2
    assert b1["n_clusters"] == 5
    assert b1["n_boot"] == 1000
    assert b1["qwk_ci_95"][0] <= b1["qwk_ci_95"][1]
    assert b1["micro_mae_ci_95"][0] <= b1["micro_mae_ci_95"][1]


def test_live_demo_v1_stratified_wiring(tmp_path: Path) -> None:
    """Verify V1_STRATIFIED and v1 rubric are wired cleanly into the FastAPI live demo endpoint."""
    import json
    from fastapi.testclient import TestClient
    from app.grading.lecturer import V1_STRATIFIED_IDS, configuration
    from app.grading.rubric import PROMPT_VERSION
    from app.grading.schemas import CRITERIA
    from app.main import create_app
    from app.providers.base import Generation
    from app.grading.aspects import ASPECT_LABELS

    assert PROMPT_VERSION == "task2-v1-calibrated"
    cfg = configuration("V1_STRATIFIED")
    assert [e["essay_id"] for e in cfg["examples"]] == V1_STRATIFIED_IDS
    assert len(cfg["examples"]) == 8

    captured: dict = {}

    class StubProvider:
        async def generate_structured(self, system_prompt, user_prompt, response_schema):
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            payload = {
                "criterion_scores": dict(zip(CRITERIA, [7.5, 7.5, 8.0, 8.0])),
                "criterion_feedback": {
                    key: {"explanation": "Strong development.", "strengths": ["Clear stance"], "weaknesses": [], "evidence": []}
                    for key in CRITERIA
                },
                "grammar_corrections": [],
                "priority_improvements": ["Refine conclusion."],
                "aspect_reviews": [
                    {"aspect": label, "score": 7.5, "explanation": "Good."} for label in ASPECT_LABELS
                ],
                "paragraph_reviews": [
                    {"paragraph_number": 1, "role": "introduction", "summary": "Clear.", "improvement": "Expand slightly.", "evidence": None}
                ],
                "language_suggestions": [],
            }
            return Generation(json.dumps(payload), "gemini-3.5-flash-lite", None, 120, {"total_token_count": 5500}, [])

        async def close(self):
            return None

    with TestClient(create_app(REPO_ROOT / "data", tmp_path / "results", lambda _: StubProvider())) as client:
        index_resp = client.get("/")
        assert index_resp.status_code == 200
        js_resp = client.get("/app.js")
        assert js_resp.status_code == 200
        assert "V1_STRATIFIED" in js_resp.text

        resp = client.post(
            "/api/writing/task2/evaluate",
            json={
                "prompt": "Some people believe cities should invest more in public transport than roads. To what extent do you agree?",
                "essay": "Public transport helps reduce urban congestion and emissions across crowded city centres.",
                "experiment": "V1_STRATIFIED",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fewshot_config"] == "V1_STRATIFIED"
        assert body["reference_example_ids"] == V1_STRATIFIED_IDS
        assert body["estimated_overall_band"] == 8.0
        assert body["confidence"]["band_margin"] == 0.5
        assert body["confidence"]["band_range_low"] == 7.5
        assert body["confidence"]["band_range_high"] == 8.5
        assert 55 <= body["confidence"]["percentage"] <= 95
        assert body["confidence"]["label"] in {"High", "Moderate", "Borderline"}
        assert "examiner judgment" in body["confidence"]["note"].lower()
        assert "NO ARTIFICIAL 8.0 CEILING" in captured["system"]
        assert "SEAMLESS, UNOBTRUSIVE cohesion" in captured["system"]
        assert "eight stratified examiner-verified references" in captured["system"].lower()


def test_band_confidence_and_half_band_range() -> None:
    """Verify deterministic confidence calibration and +/-0.5 band range under boundary & variance conditions."""
    from app.grading.schemas import Scores
    from app.grading.task2 import compute_band_confidence, overall_band

    # 1. Exact balanced mid-range essay -> High confidence, 6.5 +/- 0.5 -> [6.0, 7.0]
    s_clean = Scores(task_response=6.5, coherence_cohesion=6.5, lexical_resource=6.5, grammatical_range_accuracy=6.5)
    c_clean = compute_band_confidence(s_clean, overall_band(s_clean), 280, [])
    assert c_clean.band_range_low == 6.0 and c_clean.band_range_high == 7.0
    assert c_clean.label == "High" and c_clean.score >= 0.85

    # 2. Borderline .75 rounding boundary + wide spread + under-length -> Borderline / lower confidence
    s_edge = Scores(task_response=5.0, coherence_cohesion=6.0, lexical_resource=7.0, grammatical_range_accuracy=7.0)
    ov_edge = overall_band(s_edge)
    assert ov_edge == 6.5  # 6.25 rounds to 6.5
    c_edge = compute_band_confidence(s_edge, ov_edge, 210, ["under_250"])
    assert c_edge.band_range_low == 6.0 and c_edge.band_range_high == 7.0
    assert c_edge.score < c_clean.score
    assert c_edge.label == "Borderline"
    assert "borderline" in c_edge.note.lower()

    # 3. Clamped upper bound at 9.0 -> [8.5, 9.0]
    s_top = Scores(task_response=9.0, coherence_cohesion=9.0, lexical_resource=9.0, grammatical_range_accuracy=9.0)
    c_top = compute_band_confidence(s_top, 9.0, 300, [])
    assert c_top.band_range_low == 8.5 and c_top.band_range_high == 9.0
    assert c_top.score < 1.0  # never claim 100% certainty
