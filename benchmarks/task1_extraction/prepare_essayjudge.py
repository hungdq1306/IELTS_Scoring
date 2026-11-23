"""Prepare normalized prompt images without sending essays to the extractor."""
import argparse
import csv
import hashlib
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import io
import json
import math
import re
import random
from collections import Counter, defaultdict
from pathlib import Path

from datasets import load_dataset
from PIL import Image

from .extractor import ROOT, normalize_image
from .schemas import PromptRecord, GoldRecord


def column_key(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def human_score(row):
    scores = {}
    def visit(mapping):
        for key, value in mapping.items():
            if isinstance(value, dict):
                visit(value)
                continue
            name = column_key(key)
            if not any(s in name for s in ("score", "band", "task achievement", "task response", "ground truth")):
                continue
            try:
                number = float(value)
            except (ValueError, TypeError):
                continue
            if math.isfinite(number):
                scores[name] = number
    visit(row)
    for preferred in ("overall score", "overall band", "overall", "total score", "task achievement", "task achievement score", "task response score"):
        if preferred in scores:
            return scores[preferred]
    return sum(scores.values()) / len(scores) if scores else None


def category_from_types(source_types):
    mapping = {"line_chart": "chart_time_series", "bar_chart": "chart_static",
        "pie_chart": "chart_static", "table": "chart_static", "flow_chart": "process",
        "map": "map", "composite_chart": "mixed"}
    categories = {mapping.get(str(value).strip().lower()) for value in source_types} - {None}
    return next(iter(categories)) if len(categories) == 1 else ("mixed" if categories else None)


def scan_categories(records, destination):
    category_counts = Counter(row["visual_category_hint"] or "unclassified" for row in records)
    type_counts = Counter(kind for row in records for kind in row["source_types"])
    report = dict(unique_images=len(records), essay_count=sum(row["essay_count"] for row in records),
        category_counts=dict(sorted(category_counts.items())), source_type_counts=dict(sorted(type_counts.items())),
        map_image_hashes=[row["image_hash"] for row in records if row["visual_category_hint"] == "map"],
        method="Official source Type tags grouped by normalized hash; not independent visual classification")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "category_scan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Full unique-image categories:", json.dumps(report["category_counts"], ensure_ascii=False), flush=True)
    print("Source types:", json.dumps(report["source_type_counts"], ensure_ascii=False), flush=True)
    print(f"Map prompts available: {len(report['map_image_hashes'])}", flush=True)
    return report


def export_gold_template(records, count, destination, seed=42, drafts=None, overwrite=False):
    if count < 1 or count > len(records):
        raise ValueError("Gold sample size must be between 1 and the number of unique images")
    buckets = defaultdict(list)
    for row in records:
        if row["visual_category_hint"] is not None:
            buckets[row["visual_category_hint"]].append(row)
    if count < len(buckets):
        raise ValueError("Gold sample too small to cover all available categories")
    rng = random.Random(seed)
    for rows in buckets.values():
        rows.sort(key=lambda row: row["image_hash"])
        rng.shuffle(rows)
    chosen = []
    # Balanced strata rather than population-proportional sampling; no rare category omitted.
    while len(chosen) < count:
        progress = False
        for category in sorted(buckets):
            if buckets[category] and len(chosen) < count:
                chosen.append(buckets[category].pop())
                progress = True
        if not progress:
            raise ValueError("Not enough tagged images for requested stratified gold sample")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "gold_template.jsonl"
    if path.exists() and not overwrite:
        raise FileExistsError(f"Preserving existing template: {path}; use --overwrite-gold-template explicitly")
    rows = []
    for row in chosen:
        draft = (drafts or {}).get(row["image_hash"], {})
        rows.append(GoldRecord(image_hash=row["image_hash"], image_path=row["image_path"], prompt=row["prompt"],
            visual_category=row["visual_category_hint"], numeric_tables=draft.get("numeric_tables", []),
            spatial_or_process_steps=draft.get("spatial_or_process_steps", []),
            has_explicit_labels=draft.get("has_explicit_labels"),
            review_notes="DRAFT: inspect the image, complete every cell/step, validate source anomalies; set reviewer/date/status only after human review."))
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
    print(f"Exported {len(rows)} DRAFT gold records: {path}; strata=" + str(dict(Counter(row.visual_category for row in rows))))
    return rows


def prepare(dataset, destination, image_base):
    groups = {}
    normalized_paths = {}
    count = 0
    for split in dataset.values():
        for row in split:
            count += 1
            keys = {column_key(k): k for k in row}
            def pick(names):
                return next((row[keys[n]] for n in names if n in keys and row[keys[n]] is not None), None)
            image = pick(("image", "image path", "chart", "visual", "graph"))
            essay = pick(("essay", "essay text", "response", "answer"))
            question = pick(("question", "prompt", "task prompt", "instruction")) or ""
            if image is None or not isinstance(essay, str) or not essay.strip():
                raise ValueError(f"Row {count}: cannot map image/essay columns: {list(row)}")
            if isinstance(image, dict):
                image = Image.open(io.BytesIO(image["bytes"])) if image.get("bytes") else image.get("path")
            cache_key = None if isinstance(image, Image.Image) else str((image_base / str(image)).resolve())
            if cache_key is not None and cache_key in normalized_paths:
                image_hash, data = normalized_paths[cache_key]
            else:
                if not isinstance(image, Image.Image):
                    image = Image.open(cache_key)
                with image:
                    image_hash, data = normalize_image(image)
                if cache_key is not None:
                    normalized_paths[cache_key] = (image_hash, data)
            dest = destination / "images" / f"{image_hash}.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(data)
            score = human_score(row)
            item = groups.setdefault(image_hash, dict(image_hash=image_hash,
                image_path=str(dest.resolve()), prompt=str(question),
                silver_reference_essay=essay, silver_score=score, essay_count=0,
                source_types=[], visual_category_hint=None))
            source_type = pick(("type", "task type", "visual type"))
            if source_type and str(source_type) not in item["source_types"]:
                item["source_types"].append(str(source_type))
                item["source_types"].sort()
            item["visual_category_hint"] = category_from_types(item["source_types"])
            item["essay_count"] += 1
            if score is not None and (item["silver_score"] is None or score > item["silver_score"]):
                item.update(silver_reference_essay=essay, silver_score=score)
    if not groups:
        raise ValueError("Dataset contains no usable rows")
    destination.mkdir(parents=True, exist_ok=True)
    dest = destination / "unique_prompts.jsonl"
    temp = dest.with_suffix(".tmp")
    temp.write_text("".join(PromptRecord(**v).model_dump_json() + "\n" for v in groups.values()), encoding="utf-8")
    temp.replace(dest)
    print(f"{count} essays -> {len(groups)} unique images; saved {dest}")
    return list(groups.values())


OFFICIAL_REPOSITORY = "jsu360/EssayJudge"


def fetch_bytes(url):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "FogWrite-Task1-Benchmark"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def load_official_dataset(destination):
    """Pin the official CSV revision and retain raw images plus byte provenance."""
    source = destination / "source"
    source.mkdir(parents=True, exist_ok=True)
    metadata_path = source / "provenance.json"
    csv_path = source / "data.csv"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        revision = metadata["revision"]
    else:
        revision = json.loads(fetch_bytes(
            f"https://api.github.com/repos/{OFFICIAL_REPOSITORY}/commits/master"))["sha"]
        metadata = {"repository": f"https://github.com/{OFFICIAL_REPOSITORY}", "revision": revision}
    csv_url = f"https://raw.githubusercontent.com/{OFFICIAL_REPOSITORY}/{revision}/data.csv"
    if not csv_path.exists():
        csv_path.write_bytes(fetch_bytes(csv_url))
    raw_csv = csv_path.read_bytes()
    digest = hashlib.sha256(raw_csv).hexdigest()
    if metadata.get("csv_sha256") and metadata["csv_sha256"] != digest:
        raise ValueError("Cached official CSV checksum mismatch")
    # The published CSV uses GB18030, not UTF-8. Preserve raw bytes for provenance.
    rows = list(csv.DictReader(io.StringIO(raw_csv.decode("gb18030"))))
    urls = list(dict.fromkeys(row["graph"] for row in rows))
    image_dir = source / "images"
    image_dir.mkdir(exist_ok=True)
    prior_images = {item["url"]: item for item in metadata.get("images", [])}

    def download(url):
        if not url.startswith("https://raw.githubusercontent.com/jsu360/"):
            raise ValueError(f"Unexpected official image host: {url}")
        path = image_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".image")
        if not path.exists():
            data = fetch_bytes(url)
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            path.write_bytes(data)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if url in prior_images and prior_images[url]["sha256"] != digest:
            raise ValueError(f"Cached image checksum mismatch: {url}")
        return dict(url=url, path=str(path.resolve()), sha256=digest, size_bytes=len(data))

    print(f"Official EssayJudge: {len(rows)} rows; downloading/checking {len(urls)} unique source images", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        images = list(pool.map(download, urls))
    mapping = {image["url"]: image["path"] for image in images}
    for row in rows:
        row["image"] = mapping[row["graph"]]
    metadata.update(csv_url=csv_url, csv_sha256=digest, csv_encoding="gb18030",
        row_count=len(rows), unique_source_images=len(urls), images=images,
        silver_score_policy="Mean of available ten human ground_truth traits; not an IELTS band score")
    temporary = metadata_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(metadata_path)
    return {"train": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-name", default="EssayJudge/EssayJudge")
    parser.add_argument("--local-file")
    parser.add_argument("--source", choices=("auto", "huggingface", "github"), default="auto")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--export-gold-template", type=int)
    parser.add_argument("--gold-dir", type=Path, default=ROOT / "gold_set")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gold-draft-results", type=Path)
    parser.add_argument("--overwrite-gold-template", action="store_true")
    args, _ = parser.parse_known_args()
    preparation_started = time.perf_counter()
    source = Path(args.local_file).resolve() if args.local_file else None
    if source:
        dataset = load_dataset("parquet" if source.suffix.lower() == ".parquet" else "json", data_files=str(source))
    elif args.source == "github":
        dataset = load_official_dataset(args.data_dir.resolve())
    else:
        try:
            dataset = load_dataset(args.dataset_name)
        except Exception as exc:
            if args.source != "auto" or args.dataset_name != "EssayJudge/EssayJudge":
                raise RuntimeError("Dataset unavailable; check Hugging Face access or supply --local-file.") from exc
            print("Default Hugging Face source unavailable; using the official jsu360/EssayJudge release.", flush=True)
            dataset = load_official_dataset(args.data_dir.resolve())
    normalization_started = time.perf_counter()
    t_ingest_ms = (normalization_started-preparation_started)*1000
    records = prepare(dataset, args.data_dir.resolve(), source.parent if source else Path.cwd())
    t_normalize_group_ms = (time.perf_counter()-normalization_started)*1000
    scan_categories(records, args.data_dir.resolve())
    if args.export_gold_template:
        drafts = {}
        if args.gold_draft_results:
            from .extractor import read_jsonl, VERSION
            drafts = {row["image_hash"]: row["extraction"] for row in read_jsonl(args.gold_draft_results)
                if row.get("pipeline_version") == VERSION}
        export_gold_template(records, args.export_gold_template, args.gold_dir.resolve(),
            args.seed, drafts, args.overwrite_gold_template)
    timing = dict(t_ingest_ms=t_ingest_ms, t_normalize_group_ms=t_normalize_group_ms,
        t_prepare_total_ms=(time.perf_counter()-preparation_started)*1000,
        unique_images=len(records), cache_note="Includes checksum verification of existing source downloads")
    (args.data_dir / "preparation_timings.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
