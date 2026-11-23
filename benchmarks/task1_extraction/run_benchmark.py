"""Bound concurrent Gemini requests and checkpoint every successful extraction."""
import argparse
import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .extractor import ROOT, VERSION, append_jsonl, client, extract, read_jsonl
from .schemas import BenchmarkRecord, PromptRecord


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/v2_exhaustive_sanity")
    parser.add_argument("--allow-partial", action="store_true", help="Audit: render missing extractions explicitly; still exit nonzero")
    parser.add_argument("--select-hashes-from", type=Path, help="Select prompt hashes from a gold/template JSONL before applying --limit")
    parser.add_argument("--skip-audit", action="store_true", help="Render cached/skipped silver audit without new API calls")
    args, _ = parser.parse_known_args()
    if args.limit < 0 or args.concurrency < 1:
        parser.error("limit >= 0 and concurrency >= 1 required")
    return args


def select_prompts(args):
    records = read_jsonl(args.data_dir / "unique_prompts.jsonl")
    selection_path = getattr(args, "select_hashes_from", None)
    if selection_path:
        selected = {row["image_hash"] for row in read_jsonl(selection_path)}
        missing = selected - {row["image_hash"] for row in records}
        if not selected or missing:
            raise ValueError("Gold/hash selection is empty or contains hashes absent from the prompt manifest")
        records = [row for row in records if row["image_hash"] in selected]
    return records[:args.limit] if args.limit else records


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def summarize(results):
    groups = defaultdict(list)
    for row in results:
        groups[row["extraction"]["visual_category"]].append(row)
    print("Category                N  Auto% Check%   p50 ms   p95 ms  Mean input/output tokens")
    for category, rows in sorted(groups.items()):
        n = len(rows)
        auto = sum(row["routing_status"] == "auto_verified" for row in rows) / n * 100
        latency = [row["latency_ms"] for row in rows]
        print(f"{category:22} {n:3} {auto:6.1f} {100-auto:6.1f} "
            f"{percentile(latency, .5):8.0f} {percentile(latency, .95):8.0f} "
            f"{mean(row['prompt_tokens'] for row in rows):9.0f}/{mean(row['candidates_tokens'] for row in rows):.0f}")


async def main():
    run_started = time.perf_counter()
    args = arguments()
    path = args.output_dir / "extraction_results.jsonl"
    previous = [BenchmarkRecord.model_validate(row).model_dump() for row in read_jsonl(path)
        if row.get("pipeline_version") == VERSION and row.get("model") == args.model]
    previous = {row["image_hash"]: row for row in previous
        if row["model"] == args.model and row["pipeline_version"] == VERSION}
    records = select_prompts(args)
    if not records:
        raise RuntimeError("No prompts; run prepare_essayjudge first")
    records = [PromptRecord.model_validate(row) for row in records]
    pending = [row for row in records if row.image_hash not in previous]
    print(f"Selected {len(records)} prompts; cached {len(records)-len(pending)}; pending {len(pending)}", flush=True)
    errors = []
    semaphore = asyncio.Semaphore(args.concurrency)
    api = client() if pending else None

    async def run(record):
        async with semaphore:
            try:
                result = (await extract(api, record, args.model)).model_dump()
                append_jsonl(path, result)
                previous[record.image_hash] = result
                print(f"Saved {record.image_hash[:12]}: {result['routing_status']}; "
                    f"cells={result['sanity_report']['non_null_cells']}/{result['sanity_report']['declared_cells']}; "
                    f"attempts={result['attempt_count']}; warnings={len(result['sanity_report']['sanity_warnings'])}", flush=True)
            except Exception as exc:
                error = dict(image_hash=record.image_hash, model=args.model,
                    error_type=type(exc).__name__, message=str(exc),
                    pipeline_version=VERSION, telemetry=getattr(exc, "benchmark_telemetry", {}))
                errors.append(error)
                append_jsonl(args.output_dir / "extraction_errors.jsonl", error)
                print("Extraction failed:", record.image_hash, type(exc).__name__, flush=True)
    try:
        await asyncio.gather(*(run(record) for record in pending))
    finally:
        if api is not None:
            api.close()
    selected = {row.image_hash for row in records}
    summarize([row for key, row in previous.items() if key in selected])
    summary = dict(model=args.model, pipeline_version=VERSION, selected=len(records),
        cached_at_start=len(records)-len(pending), attempted=len(pending), failed=len(errors),
        invocation_wall_ms=(time.perf_counter()-run_started)*1000,
        latency_definition="Per-item t_total includes prepared-image validation, extraction retries and sanity; excludes queue wait, preparation and audit")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    append_jsonl(args.output_dir / "run_history.jsonl", summary)
    if errors:
        raise RuntimeError(f"{len(errors)} extractions failed; inspect extraction_errors.jsonl and rerun to resume")


if __name__ == "__main__":
    asyncio.run(main())
