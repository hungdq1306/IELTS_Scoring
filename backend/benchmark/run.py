import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout
from pydantic import ValidationError
from tqdm import tqdm

from app.config import ROOT, load_settings
from app.grading.rubric import PROMPT_VERSION, RUBRIC_VERSION, SYSTEM_PROMPT
from app.grading.detailed import DETAILED_PROMPT, DETAILED_PROMPT_VERSION
from app.grading.bands import OVERALL_POLICY
from app.grading.schemas import DetailedModelGrade, GradeRequest, ModelGrade
from app.grading.task2 import grade_essay
from app.providers.base import ProviderError
from app.providers.gemini import GeminiProvider, gemini_schema
from benchmark import store
from benchmark.datasets import LABELS, PROVENANCE, read_csv


def manifest_for(path):
    sibling = path.with_suffix(".manifest.json")
    if path.stem == "lexibot" or sibling.is_file():
        manifest = sibling
    else:
        manifest = path.parent.parent / "processed" / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}


def now():
    return datetime.now(timezone.utc).isoformat()


def make_metadata(dataset, split, count, model, file_hash, manifest, experiment="A0", kind="benchmark", essay_id=None):
    prompt, schema, version = (DETAILED_PROMPT, DetailedModelGrade, DETAILED_PROMPT_VERSION) if experiment in {"A1", "FS0", "FS1", "FS2", "FS5", "FS5_FULL", "FS5_COMPACT", "FS7"} else (SYSTEM_PROMPT, ModelGrade, PROMPT_VERSION)
    from app.grading.fewshot import configuration, CALIBRATION
    fs = configuration(experiment)
    if fs is not None:
        if experiment in {'FS5','FS5_FULL','FS5_COMPACT','FS7'}:
            from app.grading.lecturer import calibration_for
            prompt += calibration_for(experiment) + json.dumps({k:v for k,v in fs.items() if not k.startswith('_')}, sort_keys=True)
        else:
            prompt += (CALIBRATION if fs["examples"] else "") + json.dumps(fs, sort_keys=True)
        version += ":" + fs["version"] + ":" + experiment
    prompt_hash = hashlib.sha256((prompt + json.dumps(gemini_schema(schema), sort_keys=True)).encode()).hexdigest()
    config = {
        "dataset": dataset, "dataset_revision": manifest.get("revision"),
        "label_provenance": manifest.get("label_provenance", PROVENANCE),
        "split": split, "expected": count, "model": model, "dataset_sha256": file_hash,
        "experiment": experiment, "prompt_version": version, "overall_policy": OVERALL_POLICY,
        "rubric_version": RUBRIC_VERSION, "prompt_sha256": prompt_hash,
        "kind": kind, "selected_essay_id": essay_id, "provider": "gemini",
        "parameters": {"temperature": 0, "max_output_tokens": 8192},
    }
    if fs is not None:
        config["fewshot"] = {k:v for k,v in fs.items() if k != "examples" and not k.startswith('_')}
        config["fewshot"]["reference_example_ids"] = [r["essay_id"] for r in fs["examples"]]
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    return {**config, "run_id": f"{experiment.lower()}-{key}", "created_at": now()}


def base_row(essay):
    return {
        "essay_id": essay["essay_id"], "prompt": essay["prompt"], "essay": essay["essay"],
        "gold": {name.removeprefix("gold_"): essay[name] for name in LABELS},
        "topic": essay["topic"], "word_count": essay["word_count"], "quality_flags": essay["quality_flags"],
        "timestamp": now(), "prediction": None, "attempts": [], "error": None, "status": "pending",
    }


async def evaluate_record(essay, provider, *, detailed=False, experiment=None):
    row = base_row(essay)
    raw = None
    try:
        request = GradeRequest(prompt=essay["prompt"], essay=essay["essay"], topic=essay["topic"])
        prediction, generation = await grade_essay(request, provider, detailed=detailed, experiment=experiment)
        raw = generation.raw
        row.update(status="ok", prediction=prediction.model_dump(),
                   attempts=[item.model_dump() for item in generation.attempts])
    except ValidationError:
        row.update(status="invalid_input", error="Essay did not pass grading input validation.")
    except ProviderError as exc:
        raw = exc.generation.raw if exc.generation is not None else None
        row.update(status=exc.code, error=exc.message, attempts=[item.model_dump() for item in exc.attempts])
    return row, raw


def pending_essays(essays, latest, retry_failures=False):
    finished = {row["essay_id"] for row in latest
                if row["status"] == "ok" or (row["status"] == "invalid_input" or (
                    not retry_failures and row["status"] not in {
                        "local_daily_budget", "daily_quota", "rate_limited", "local_rate_limit",
                        "request_budget", "gemini_configuration", "connection_error", "timeout", "upstream_unavailable",
                    }
                ))}
    return [essay for essay in essays if essay["essay_id"] not in finished]


async def run(args, settings):
    manifest = manifest_for(args.dataset)
    file_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if args.dataset.stem == "test_locked":
        expected_hash = manifest.get("splits", {}).get("test_locked", {}).get("sha256")
        if file_hash != expected_hash:
            raise ValueError("Locked test file hash does not match its dataset manifest.")
    if args.dataset.stem == "lexibot" and file_hash != manifest.get("csv_sha256"):
        raise ValueError("Lexibot CSV does not match its reference manifest. Rebuild with benchmark.lexibot.")
    essays = read_csv(args.dataset)[:args.max_samples]
    if not essays or len({essay["essay_id"] for essay in essays}) != len(essays):
        raise ValueError("Provide at least one essay with unique essay IDs.")
    if args.experiment in {"FS0", "FS1", "FS2", "FS5", "FS5_FULL", "FS5_COMPACT", "FS7"}:
        from app.grading.fewshot import configuration, protect
        config = configuration(args.experiment)
        for essay in essays:
            protect(GradeRequest(prompt=essay["prompt"], essay=essay["essay"]), config)
    metadata = make_metadata(essays[0]["source_dataset"], args.dataset.stem,
                             len(essays), settings.model, file_hash, manifest, args.experiment)
    path = args.results / f"{metadata['run_id']}.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=0):
        return await run_locked(args, settings, essays, metadata, path)


async def run_locked(args, settings, essays, metadata, path):
    if path.exists() and not args.resume:
        raise ValueError(f"Run already exists: {metadata['run_id']}. Pass --resume.")
    provider = GeminiProvider(settings, generation_budget=args.request_budget)
    try:
        available = await provider.available_models()
        if settings.model not in available:
            raise ProviderError("model_unavailable", "Configured model is unavailable for the API key.")
        store.initialize(path, metadata)
        _, latest, _ = store.read(path)
        pending = pending_essays(essays, latest, args.retry_failures)
        stop = {
            "daily_quota", "local_daily_budget", "request_budget", "rate_limited", "local_rate_limit",
            "gemini_configuration", "connection_error", "timeout", "upstream_unavailable",
        }
        deferred = False
        for essay in tqdm(pending[:getattr(args, "max_new_essays", None)], desc=metadata["run_id"], unit="essay"):
            if metadata.get("fewshot"):
                from app.grading.fewshot import configuration
                current = configuration(args.experiment)
                if current["reference_sha256"] != metadata["fewshot"]["reference_sha256"]:
                    raise ValueError("Reference snapshot changed during the run; stop and create a new experiment version")
            row, raw = await evaluate_record(essay, provider, detailed=args.experiment == "A1", experiment=args.experiment)
            store.add(path, row, raw)
            if (args.defer_unavailable and row["status"] == "upstream_unavailable"
                    and row["attempts"] and row["attempts"][-1]["api_code"] == 503):
                deferred = True
                tqdm.write(f"Deferred {row['essay_id']} after HTTP 503. Continue remaining essays.")
                continue
            if row["status"] in stop:
                tqdm.write(f"Paused at {row['essay_id']}: {row['error']} Resume with the same arguments and --resume.")
                return path, False
        _, saved, _ = store.read(path)
        return path, not deferred and sum(row["status"] == "ok" for row in saved) == len(essays)
    finally:
        await provider.close()


def main():
    parser = argparse.ArgumentParser(description="Run a reproducible IELTS Task 2 benchmark.")
    parser.add_argument("--dataset", default=ROOT / "data/splits/dev.csv", type=Path)
    parser.add_argument("--experiment", choices=["A0", "A1", "FS0", "FS1", "FS2", "FS5", "FS5_FULL", "FS5_COMPACT", "FS7"], default="A0")
    parser.add_argument("--provider", choices=["gemini"], default="gemini")
    parser.add_argument("--max-samples", type=int)
    parser.add_argument("--max-new-essays", type=int, help="Limit newly evaluated essays without changing run identity.")
    parser.add_argument("--request-budget", type=int, help="Cap this invocation, including provider retries.")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--defer-unavailable", action="store_true",
                        help="Continue after exhausted HTTP 503 retries; revisit deferred essays on resume.")
    args = parser.parse_args()
    if any(value is not None and value <= 0 for value in (args.max_samples, args.max_new_essays, args.request_budget)):
        parser.error("Sample limits and request budgets must be positive.")
    try:
        path, complete = asyncio.run(run(args, load_settings()))
        print(f"Run database: {path}")
        if not complete:
            parser.exit(2)
    except (ValueError, OSError, Timeout, ProviderError) as exc:
        parser.exit(1, f"Benchmark failed: {exc}\n")


if __name__ == "__main__":
    main()
