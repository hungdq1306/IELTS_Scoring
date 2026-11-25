import json
from pathlib import Path
from src.data.records import load_records, verified_records
from src.eval.prompt_v1 import select_stratified_anchors, build_user_prompt_v1
from app.grading.lecturer import configuration
from app.grading.payload import project_anchor

ROOT = Path(__file__).resolve().parents[1]


def test_teacher_pool_matches_source_annotations_without_fixed_ids():
    records = load_records(ROOT/'artifacts/dataset_v1/seed.jsonl')
    source = json.loads((ROOT/'data/lecturer/manifests/fs7_v1.json').read_text(encoding='utf-8'))
    expected = {r['essay_id'] for r in source['examples'] if r['label_provenance']=='explicit_lecturer_annotation' and r['prompt_verified']}
    pool = verified_records(records)
    assert {r.essay_id for r in pool} == expected
    assert {r['essay_id'] for r in configuration('V1_STRATIFIED')['examples']} == expected
    assert any(r.tr != r.cc for r in pool)
    ai = [r for r in records if r.score_source=='ai_augmented']
    assert len(ai) == len(records) - len(pool) - len([r for r in records if r.score_source=='dual_rater'])
    assert all(r.quality_tier=='ai_augmented' and not r.score_provenance['independently_verified'] for r in ai)
    renamed = [r.model_copy(update={'essay_id':f'opaque-{i}'}) for i,r in enumerate(records)]
    assert len(select_stratified_anchors(renamed)) == len(pool)
    assert all(r.essay_id.startswith('opaque-') for r in select_stratified_anchors(renamed))


def test_eval_projection_has_no_overall_or_legacy_cue():
    rows = load_records(ROOT/'artifacts/dataset_v1/seed.jsonl')
    target = rows[0]
    payload = json.loads(build_user_prompt_v1(target, rows[1:]))
    assert payload['NEW ESSAY']['student_essay']
    for anchor in payload['REFERENCE EXAMPLES']:
        assert set(anchor['scores']) == {'task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'}
        assert 'examiner_calibration_cue' not in anchor
        assert anchor['provenance']['independently_verified'] is True
        assert anchor['feedback_by_criterion']
        if anchor['metadata']['paragraph_boundary_verified']:
            assert anchor['student_essay'].startswith('[p1]\n')


def test_reported_score_kept_separate_from_computed():
    rows = load_records(ROOT/'artifacts/dataset_v1/seed.jsonl')
    row = next(r for r in rows if (r.tr,r.cc,r.lr,r.gra)==(8,8,8,7))
    assert row.overall_reported == row.overall_computed == row.overall == 7.5
    assert any(r.overall_reported != r.overall_computed for r in rows)
