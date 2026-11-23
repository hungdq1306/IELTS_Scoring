"""Bound concurrent Gemini requests and checkpoint every successful extraction."""
import argparse
import asyncio
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .extractor import ROOT, VERSION, append_jsonl, client, extract, read_jsonl
from .schemas import BenchmarkRecord, PromptRecord


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args, _ = parser.parse_known_args()
    if args.limit < 0 or args.concurrency < 1:
        parser.error("limit >= 0 and concurrency >= 1 required")
    return args


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
    args = arguments()
    path = args.output_dir / "extraction_results.jsonl"
    previous = [BenchmarkRecord.model_validate(row).model_dump() for row in read_jsonl(path)]
    previous = {row["image_hash"]: row for row in previous
        if row["model"] == args.model and row["pipeline_version"] == VERSION}
    records = read_jsonl(args.data_dir / "unique_prompts.jsonl")
    if not records:
        raise RuntimeError("No prompts; run prepare_essayjudge first")
    records = records[:args.limit] if args.limit else records
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
                print(f"Saved {record.image_hash[:12]}: {result['routing_status']}", flush=True)
            except Exception as exc:
                error = dict(image_hash=record.image_hash, model=args.model,
                    error_type=type(exc).__name__, message=str(exc))
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
    if errors:
        raise RuntimeError(f"{len(errors)} extractions failed; inspect extraction_errors.jsonl and rerun to resume")


if __name__ == "__main__":
    asyncio.run(main())
