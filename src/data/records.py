"""Read frozen split bytes through a policy-specific metadata view; never rewrite them."""
import hashlib
import json
from pathlib import Path
from src.data.tiering import EssayRecord, compute_ielts_overall


def load_records(path):
    path = Path(path)
    audit_path = path.parent / 'paragraph_audit.jsonl'
    audit = {r['essay_id']: r for r in (json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines())} if audit_path.exists() else {}
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        note = audit.get(row['essay_id'])
        if note:
            if hashlib.sha256(row['essay'].encode()).hexdigest() != note['essay_sha256']:
                raise ValueError('Paragraph metadata belongs to a different essay snapshot')
            row['paragraph_boundary_verified'] = note['paragraph_boundary_verified']
            row['paragraph_boundary_source'] = note['paragraph_boundary_source']
        row['overall_computed'] = compute_ielts_overall(*(row[c] for c in ('tr','cc','lr','gra')))
        row['overall'] = row['overall_computed']
        row['overall_policy'] = 'half_band_threshold_0375_v1'
        rows.append(EssayRecord.model_validate(row))
    return sorted(rows, key=lambda r: r.essay_id)


def verified_records(records):
    return [r for r in records if r.score_source == 'examiner_verified'
            and r.score_provenance.get('independently_verified') is True and r.examiner_feedback]


def check_membership(rows, split, directory):
    manifest = json.loads((Path(directory) / 'frozen_membership.json').read_text(encoding='utf-8'))
    expected = {r['essay_id']: r for r in manifest['splits'][split]['records']}
    if len(rows) != len(expected) or {r.essay_id for r in rows} != set(expected):
        raise ValueError(f'{split} membership differs from the frozen manifest')
    for row in rows:
        ref = expected[row.essay_id]
        if row.prompt_cluster_id != ref['prompt_cluster_id'] or hashlib.sha256(row.essay.encode()).hexdigest() != ref['essay_sha256']:
            raise ValueError(f'{split} content or cluster differs from frozen manifest')
