import hashlib
import json
import subprocess
from pathlib import Path
import pytest
from src.data.records import load_records, check_membership
from src.data.splitter import run_split_pipeline

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'artifacts/dataset_v1'


def test_frozen_bytes_membership_clusters_and_text():
    manifest = json.loads((DATA/'frozen_membership.json').read_text())
    for split in ('seed','dev','holdout'):
        raw = (DATA/f'{split}.jsonl').read_bytes()
        if split != 'seed':
            policy=subprocess.run(['git','config','--get','core.autocrlf'],capture_output=True,text=True,check=False).stdout.strip()
            # Git's existing checkout policy controls EOLs. This is not an allowance
            # to change file bytes within a checkout: the expected hash is fixed.
            field='sha256_before_hygiene' if policy=='true' else 'git_blob_sha256_before_hygiene'
            assert hashlib.sha256(raw).hexdigest() == manifest['splits'][split][field]
            assert hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest() == manifest['splits'][split]['git_blob_sha256_before_hygiene']
        rows = load_records(DATA/f'{split}.jsonl')
        check_membership(rows, split, DATA)
        stored = [json.loads(l) for l in raw.decode().splitlines()]
        assert [r['essay_id'] for r in stored] == [r['essay_id'] for r in manifest['splits'][split]['records']]
        for row, ref in zip(stored, manifest['splits'][split]['records']):
            assert hashlib.sha256(row['prompt'].encode()).hexdigest() == ref['prompt_sha256']
        assert hashlib.sha256((DATA/f'{split}.jsonl').read_bytes()).hexdigest() == hashlib.sha256(raw).hexdigest()


def test_paragraph_sidecar_is_targeted_and_unverified():
    notes = [json.loads(l) for l in (DATA/'paragraph_audit.jsonl').read_text().splitlines()]
    assert len(notes) == 12
    assert {s:sum(n['split']==s for n in notes) for s in ('seed','dev','holdout')} == {'seed':4,'dev':7,'holdout':1}
    assert all(n['paragraph_boundary_verified'] is False for n in notes)
    assert sum(n['verification_status']=='no_boundaries' for n in notes)==3
    assert all('essay' not in n for n in notes)


def test_frozen_splitter_refuses_overwrite():
    with pytest.raises(ValueError, match='Frozen dataset'):
        run_split_pipeline(ROOT/'configs/dataset_split.yaml',root=ROOT)
