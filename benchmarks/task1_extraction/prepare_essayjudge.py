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
from pathlib import Path

from datasets import load_dataset
from PIL import Image

from .extractor import ROOT, normalize_image
from .schemas import PromptRecord


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
                silver_reference_essay=essay, silver_score=score, essay_count=0))
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
    args, _ = parser.parse_known_args()
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
    prepare(dataset, args.data_dir.resolve(), source.parent if source else Path.cwd())


if __name__ == "__main__":
    main()
