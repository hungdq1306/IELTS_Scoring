"""Prepare normalized prompt images without sending essays to the extractor."""
import argparse
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
            if not any(s in name for s in ("score", "band", "task achievement", "task response")):
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
    count = 0
    for split in dataset.values():
        for row in split:
            count += 1
            keys = {column_key(k): k for k in row}
            def pick(names):
                return next((row[keys[n]] for n in names if n in keys and row[keys[n]] is not None), None)
            image = pick(("image", "image path", "chart", "visual"))
            essay = pick(("essay", "essay text", "response", "answer"))
            question = pick(("question", "prompt", "task prompt", "instruction")) or ""
            if image is None or not isinstance(essay, str) or not essay.strip():
                raise ValueError(f"Row {count}: cannot map image/essay columns: {list(row)}")
            if isinstance(image, dict):
                image = Image.open(io.BytesIO(image["bytes"])) if image.get("bytes") else image.get("path")
            if not isinstance(image, Image.Image):
                image = Image.open(image_base / str(image))
            with image:
                image_hash, data = normalize_image(image)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-name", default="EssayJudge/EssayJudge")
    parser.add_argument("--local-file")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args, _ = parser.parse_known_args()
    source = Path(args.local_file).resolve() if args.local_file else None
    try:
        dataset = load_dataset("parquet" if source.suffix.lower() == ".parquet" else "json", data_files=str(source)) if source else load_dataset(args.dataset_name)
    except Exception as exc:
        raise RuntimeError("Dataset unavailable. Check --dataset-name / HF authentication, or supply --local-file JSON/JSONL/Parquet with images and human scores.") from exc
    prepare(dataset, args.data_dir.resolve(), source.parent if source else Path.cwd())


if __name__ == "__main__":
    main()
