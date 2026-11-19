import asyncio
import json
import random
from collections import defaultdict
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from pydantic import ValidationError

from app.config import Settings
from app.grading.schemas import CRITERIA, GradeRequest, ModelGrade, Scores
from app.grading.task2 import overall_band, validate_grade
from app.main import create_app
from app.providers.base import Generation, ProviderError
from app.providers.gemini import GeminiProvider, RequestBudget, classify_error
from benchmark import store
from benchmark.datasets import LABELS, clean, near_duplicate_pairs, parse_band, split_rows, write_csv
from benchmark.metrics import quadratic_kappa, score_metrics
from benchmark.run import make_metadata, pending_essays


def payload():
    return {
        "criterion_scores": dict(zip(CRITERIA, [6, 6, 6.5, 6.5])),
        "criterion_feedback": {key: {
            "explanation": "Assess the development.",
            "strengths": [], "weaknesses": [],
            "evidence": [{"quote": "Public transport", "explanation": "Grounded"},
                         {"quote": "Invented quote", "explanation": "Ungrounded"}],
        } for key in CRITERIA},
        "grammar_corrections": [{"original": "Invented span", "corrected": "Correction", "explanation": "Ungrounded"}],
        "priority_improvements": ["Explain the example."],
    }


def generation(raw=None):
    return Generation(raw if raw is not None else json.dumps(payload()), "test-fixture", None, 23, {}, [])


def sample():
    return GradeRequest(prompt="Do you agree or disagree with investing in public transport?",
                        essay="Public transport can improve access.")


@pytest.mark.parametrize("value", [True, None, "x", "NaN", 9.5, -0.5, 6.2])
def test_reject_bad_band(value):
    with pytest.raises((TypeError, ValueError)):
        parse_band(value)


def test_model_schema_and_grounding():
    request = sample()
    assert overall_band(Scores(**payload()["criterion_scores"])) == 6.5
    result = validate_grade(generation(), request, 25)
    assert result.word_count == 5
    assert result.criterion_feedback.task_response.evidence[0].quote == "Public transport"
    assert len(result.criterion_feedback.task_response.evidence) == 1
    assert not result.grammar_corrections
    assert len(result.validation_warnings) == 6
    with pytest.raises(ProviderError, match="unusable") as bad:
        validate_grade(generation("{"), request, 25)
    assert bad.value.code == "invalid_json"
    missing = payload()
    del missing["criterion_scores"]["task_response"]
    with pytest.raises(ValidationError):
        ModelGrade.model_validate(missing)


def test_dataset_dedup_and_retains_original_label():
    from datasets import Dataset

    words = " ".join(f"vocabulary{i}" for i in range(75))
    first = {"essay_id": "1", "question": "Should education be free for everyone?", "essay_text": words, "topic": "Education"}
    first.update({field: 7 for field in LABELS.values()})
    data = Dataset.from_list([
        first, {**first, "essay_id": "2", "essay_text": words.upper()},
        {**first, "essay_id": "3", "essay_text": words + " extra words"},
        {**first, "essay_id": "4", "essay_text": "Short essay."},
        {**first, "essay_id": "5", "overall_band": 4.2},
    ])
    rows, summary, issues = clean(data)
    assert [row["essay_id"] for row in rows] == ["1"]
    assert rows[0]["gold_overall"] == 7
    assert summary["filtering"]["near_duplicate_removed"] == 1
    assert {item["flag"] for item in issues} == {"exact_duplicate", "near_duplicate_pair", "very_short", "invalid_label"}


def test_jaccard_search_matches_brute_force():
    rng = random.Random(42)
    roots = [rng.choices("abcdefghijklmn", k=60) for _ in range(8)]
    tokens = [row[:20] + rng.choices("abcdef", k=i % 4) + row[20:] for row in roots for i in range(8)]
    sets = [set(zip(*(row[i:] for i in range(5)))) for row in tokens]
    expected = {(i, j) for j in range(len(sets)) for i in range(j)
                if len(sets[i] & sets[j]) / len(sets[i] | sets[j]) >= .85}
    assert {(i, j) for i, j, _ in near_duplicate_pairs([" ".join(row) for row in tokens])} == expected


def test_split_isolation():
    rows = [{"essay_id": str(i), "prompt_group": i % 50, "gold_overall": 4 + i % 9 / 2} for i in range(750)]
    splits = split_rows(rows)
    assert [len(rows) for rows in splits.values()] == [5, 30, 100]
    assert splits == split_rows(list(reversed(rows)))
    group_membership = defaultdict(set)
    for split, essays in splits.items():
        for essay in essays:
            group_membership[essay["prompt_group"]].add(split)
    assert max(map(len, group_membership.values())) == 1


def test_metrics():
    metrics = score_metrics([(5, 6), (6, 5.5), (7, 7)])
    assert metrics["mae"] == 0.5
    assert metrics["rmse"] == pytest.approx((1.25 / 3) ** .5)
    assert metrics["within_05"] == 2 / 3
    assert metrics["bias"] == pytest.approx(1 / 6)
    assert quadratic_kappa([(5, 5), (5, 5)]) is None
    assert quadratic_kappa([(5, 5), (6, 6)]) == 1
    assert quadratic_kappa([(5, 6), (6, 5)]) == -1


def test_resume(tmp_path):
    db = tmp_path / "test.sqlite3"
    meta = make_metadata("test", "dev", 3, "test-model", "hash", {})
    essays = [{"essay_id": item} for item in "abc"]
    store.initialize(db, meta)
    store.add(db, {**essays[0], "status": "ok"}, "raw")
    store.add(db, {**essays[1], "status": "rate_limited"})
    store.add(db, {**essays[2], "status": "invalid_json"})
    assert pending_essays(essays, store.read(db)[1]) == essays[1:2]
    assert pending_essays(essays, store.read(db)[1], True) == essays[1:]
    assert store.export(db)[0][2] == "raw"


def test_daily_budget_and_retry(tmp_path, monkeypatch):
    def quota(message, headers=None):
        return errors.ClientError(429, {"error": {"message": message, "status": "RESOURCE_EXHAUSTED"}},
                                  SimpleNamespace(headers=headers or {}))

    assert classify_error(quota("GenerateContentRequestsPerDay")).code == "daily_quota"
    assert classify_error(quota("Per minute", {"retry-after": "2"})).retry_after == 2
    budget = RequestBudget(tmp_path / "quota.sqlite3", Settings(daily_budget=1))
    assert budget.reserve() == 0
    with pytest.raises(ProviderError) as exc:
        budget.reserve()
    assert exc.value.code == "local_daily_budget"

    calls = []

    async def generate_content(**_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise quota("Per minute")
        return SimpleNamespace(text=json.dumps(payload()), usage_metadata=None, model_version="fixture",
                               candidates=[SimpleNamespace(finish_reason="STOP")])

    async def ignore(*_args):
        pass

    provider = GeminiProvider(Settings(api_key="fixture"),
                              client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))))
    monkeypatch.setattr(provider.budget, "acquire", ignore)
    monkeypatch.setattr(asyncio, "sleep", ignore)
    result = asyncio.run(provider.generate_structured("rubric", "input", ModelGrade))
    assert [attempt.status for attempt in result.attempts] == ["rate_limited", "ok"]


def test_http_endpoints_and_saved_dataset_result(tmp_path):
    class FakeProvider:
        async def close(self):
            pass

        async def generate_structured(self, *_args):
            return generation(json.dumps({
                **payload(), "aspect_reviews": [], "paragraph_reviews": [], "language_suggestions": [],
            }))

    row = {"essay_id": "essay-1", **sample().model_dump(), **{key: 6 for key in LABELS},
           "source_dataset": "fixture", "prompt_group": "group", "quality_flags": "", "word_count": 6}
    write_csv(tmp_path / "data" / "splits" / "smoke.csv", [row])
    with TestClient(create_app(tmp_path / "data", tmp_path / "results", lambda _: FakeProvider())) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/datasets/smoke/essays").json()["total"] == 1
        assert client.get("/api/datasets/smoke/essays/essay-1").status_code == 200
        assert client.get("/api/benchmarks").json() == []
        assert client.post("/api/writing/task2/evaluate", json={"prompt": "hi", "essay": ""}).status_code == 422
        source = {"split": "smoke", "essay_id": row["essay_id"]}
        response = client.post("/api/writing/task2/evaluate", json={**sample().model_dump(), "source": source})
        assert response.status_code == 200, response.text
        run_id = response.json()["saved_run_id"]
        assert client.get(f"/api/benchmarks/{run_id}").json()["summary"]["completed"] == 1
        assert client.get(f"/api/benchmarks/{run_id}/results").json()[0]["essay_id"] == row["essay_id"]


@pytest.mark.parametrize("failures,expected", [(2, ["upstream_unavailable", "upstream_unavailable", "ok"]),
                                                (5, ["upstream_unavailable"] * 5)])
def test_web_retry_recovery_and_exhaustion(tmp_path, monkeypatch, failures, expected):
    calls, waits, reservations = [], [], []

    async def generate_content(**kwargs):
        calls.append(kwargs)
        if len(calls) <= failures:
            raise errors.ServerError(503, {"error": {"message": "Unavailable", "status": "UNAVAILABLE"}})
        return SimpleNamespace(text=json.dumps(payload()), usage_metadata=None, model_version="fixture",
                               candidates=[SimpleNamespace(finish_reason="STOP")])

    async def acquire():
        reservations.append(True)

    async def sleep(delay):
        waits.append(delay)

    provider = GeminiProvider(Settings(api_key="fixture", retries=4), tmp_path / "quota.sqlite3",
        client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))))
    monkeypatch.setattr(provider.budget, "acquire", acquire)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    if failures < 5:
        result = asyncio.run(provider.generate_structured("rubric", "essay", ModelGrade))
        attempts = result.attempts
    else:
        with pytest.raises(ProviderError) as caught:
            asyncio.run(provider.generate_structured("rubric", "essay", ModelGrade))
        assert caught.value.status == 503
        assert "5 attempts" in caught.value.message
        attempts = caught.value.attempts
    assert [item.status for item in attempts] == expected
    assert len(reservations) == len(calls) == len(expected)
    assert all(calls[0] == call for call in calls)
    assert all(min(30, 5 * 2**index) <= delay <= min(30, 5 * 2**index) + .5
               for index, delay in enumerate(waits))
