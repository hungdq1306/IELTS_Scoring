import argparse
import csv
import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from pydantic import ValidationError

from app.config import ROOT
from app.grading.schemas import GradeRequest, WORDS, word_count
from app.grading.task2 import overall_band
from app.grading.schemas import Scores

PRIMARY = "chillies/ielts-writing-task2-essays"
SECONDARY = "chillies/IELTS-writing-task-2-evaluation"
PROVENANCE = (
    "Primary labels are Writing9 proxy scores. The annotation method for individual rows "
    "and qualified examiner verification are unconfirmed."
)
LABELS = {
    "gold_overall": "overall_band",
    "gold_tr": "task_achievement_band",
    "gold_cc": "coherence_cohesion_band",
    "gold_lr": "lexical_resource_band",
    "gold_gra": "grammatical_range_band",
}
FIELDS = (
    "essay_id", "prompt", "essay", *LABELS, "source_dataset", "topic", "word_count",
    "prompt_group", "quality_flags",
)
SEED = 42
SPLIT_SIZES = {"smoke": 5, "dev": 30, "test_locked": 100}
NEAR_THRESHOLD = 0.85
MIN_WORDS = 40


def normalize(text: str) -> str:
    return " ".join(WORDS.findall(unicodedata.normalize("NFKC", text).casefold()))


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_band(value) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean band")
    band = float(value)
    if not math.isfinite(band) or not 0 <= band <= 9 or band * 2 % 1 != 0:
        raise ValueError(f"invalid band: {value!r}")
    return band


def near_duplicate_pairs(texts: list[str], threshold: float = NEAR_THRESHOLD):
    """Complete Jaccard threshold search over normalized word 5-grams."""
    grams = []
    for text in texts:
        tokens = text.split()
        grams.append(set(zip(*(tokens[i:] for i in range(5)))) or {tuple(tokens)})
    frequencies = Counter(gram for row in grams for gram in row)
    inverted = defaultdict(list)
    for index, row in enumerate(grams):
        prefix = sorted(row, key=lambda gram: (frequencies[gram], gram))[:len(row) - math.ceil(threshold * len(row)) + 1]
        candidates = {other for gram in prefix for other in inverted[gram]}
        for other in sorted(candidates):
            second = grams[other]
            if min(len(row), len(second)) < threshold * max(len(row), len(second)):
                continue
            overlap = len(row & second)
            similarity = overlap / (len(row) + len(second) - overlap)
            if similarity >= threshold:
                yield other, index, similarity
        for gram in prefix:
            inverted[gram].append(index)


def clean(rows):
    required = {"essay_id", "question", "essay_text", *LABELS.values()}
    schema = {key: str(value) for key, value in rows.features.items()}
    missing = required - set(schema)
    if missing:
        raise ValueError(f"Primary dataset schema is missing {sorted(missing)}. Found {schema}.")

    stats = Counter()
    flags_count = Counter()
    invalid_labels = Counter()
    issues = []
    candidates = []
    seen_essays, seen_ids = {}, set()
    for row in rows:
        stats["raw"] += 1
        essay_id = str(row["essay_id"] or "").strip()
        prompt, essay = row["question"], row["essay_text"]
        reject = None
        if not essay_id or not isinstance(prompt, str) or not prompt.strip() or not isinstance(essay, str) or not essay.strip():
            reject = "missing_required_value"
        elif any(row[key] in (None, "") for key in LABELS.values()):
            reject = "missing_label"
        else:
            bands = {}
            for target, source in LABELS.items():
                try:
                    bands[target] = parse_band(row[source])
                except (ValueError, TypeError, OverflowError):
                    invalid_labels[source] += 1
            if len(bands) != len(LABELS):
                reject = "invalid_label"
        if reject:
            stats[reject] += 1
            issues.append({"essay_id": essay_id, "flag": reject})
            continue
        try:
            request = GradeRequest(prompt=prompt, essay=essay, topic=str(row.get("topic") or ""))
        except ValidationError:
            stats["unsupported_text_size"] += 1
            issues.append({"essay_id": essay_id, "flag": "unsupported_text_size"})
            continue
        count = word_count(request.essay)
        if count < MIN_WORDS:
            stats["very_short"] += 1
            issues.append({"essay_id": essay_id, "flag": "very_short"})
            continue
        essay_norm = normalize(request.essay)
        prompt_norm = normalize(request.prompt)
        previous = seen_essays.get(essay_norm)
        if previous:
            stats["exact_duplicate"] += 1
            different = any(bands[key] != previous[key] for key in bands)
            issues.append({"essay_id": essay_id, "flag": "exact_duplicate", "related": previous["essay_id"], "conflicting_labels": different})
            stats["duplicate_label_conflicts"] += different
            continue
        if essay_id in seen_ids:
            stats["reused_essay_id"] += 1
            issues.append({"essay_id": essay_id, "flag": "reused_essay_id"})
            continue

        flags = []
        if count < 250:
            flags.append("under_250_words")
        if count > 600:
            flags.append("over_600_words")
        if prompt_norm and essay_norm.startswith(prompt_norm):
            flags.append("prompt_copied_at_start")
        if re.search(r"[\ufffd\x00]", request.essay):
            flags.append("possible_text_corruption")
        key_terms = {word for word in prompt_norm.split() if len(word) >= 7}
        if len(key_terms) >= 3 and not key_terms.intersection(essay_norm.split()):
            flags.append("no_long_prompt_term_overlap_unverified")
        scores = Scores(**dict(zip(Scores.model_fields, (bands[key] for key in LABELS if key != "gold_overall"))))
        if abs(overall_band(scores) - bands["gold_overall"]) >= 0.5:
            flags.append("reported_overall_differs_from_mvp_formula")
        if not min(scores.model_dump().values()) <= bands["gold_overall"] <= max(scores.model_dump().values()):
            flags.append("overall_outside_criterion_range")
        if bands["gold_overall"] == 0:
            flags.append("zero_band_with_substantial_text")
        flags_count.update(flags)
        entry = {
            "essay_id": essay_id, "prompt": request.prompt, "essay": request.essay,
            **bands, "source_dataset": PRIMARY, "topic": request.topic, "word_count": count,
            "prompt_group": fingerprint(prompt_norm)[:16], "quality_flags": "|".join(flags),
        }
        candidates.append(entry)
        seen_ids.add(essay_id)
        seen_essays[essay_norm] = entry

    parents = list(range(len(candidates)))

    def root(i):
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for left, right, similarity in near_duplicate_pairs([normalize(row["essay"]) for row in candidates]):
        left_root, right_root = sorted((root(left), root(right)))
        parents[right_root] = left_root
        source, copy = candidates[left], candidates[right]
        if source["prompt_group"] != copy["prompt_group"]:
            stats["near_duplicate_cross_prompt_pairs"] += 1
        issues.append({"essay_id": copy["essay_id"], "flag": "near_duplicate_pair", "related": source["essay_id"], "similarity": round(similarity, 4)})

    unique = [row for index, row in enumerate(candidates) if index == root(index)]
    stats["near_duplicate_removed"] = len(candidates) - len(unique)
    stats["kept"] = len(unique)
    summary = {
        "schema": schema, "source_label_fields": LABELS, "filtering": dict(stats),
        "invalid_label_fields": dict(invalid_labels), "quality_flags_before_near_dedup": dict(flags_count),
    }
    return unique, summary, issues


def distribution(rows):
    return dict(sorted(Counter(row["gold_overall"] for row in rows).items()))


def split_rows(rows, seed=SEED, sizes=SPLIT_SIZES):
    rng = random.Random(seed)
    pool = sorted(rows, key=lambda row: row["essay_id"])
    rng.shuffle(pool)
    coverage = defaultdict(set)
    for row in pool:
        coverage[row["gold_overall"]].add(row["prompt_group"])
    assigned = {}
    outputs = {}
    ordered_bands = sorted(row["gold_overall"] for row in pool)
    # Use empirical quantiles for smoke and balanced bands for development and test.
    for name, limit in sizes.items():
        counts = Counter()
        selected = []
        for index in range(limit):
            candidates = [row for row in pool if assigned.get(row["prompt_group"], name) == name]
            if not candidates:
                break
            quantile = ordered_bands[int((index + 0.5) * len(ordered_bands) / limit)]
            chosen = min(candidates, key=lambda row: (
                abs(row["gold_overall"] - quantile) if name == "smoke" else 0,
                counts[row["gold_overall"]],
                len(coverage[row["gold_overall"]]),
                0 if row["prompt_group"] in assigned else 1,
            ))
            assigned[chosen["prompt_group"]] = name
            counts[chosen["gold_overall"]] += 1
            selected.append(chosen)
            pool.remove(chosen)
        outputs[name] = selected
    return outputs


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        result = list(csv.DictReader(stream))
    for row in result:
        for key in LABELS:
            row[key] = parse_band(row[key])
        row["word_count"] = int(row["word_count"])
    return result


def write_csv(path: Path, rows) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(args):
    from datasets import load_dataset

    revision = args.revision
    if args.local_file:
        fmt = {".parquet": "parquet", ".csv": "csv", ".jsonl": "json", ".json": "json"}
        if args.local_file.suffix.lower() == ".parquet":
            from datasets import Dataset
            import pyarrow.parquet as parquet

            # Read Arrow types directly so older datasets can load newer HF list metadata.
            table = parquet.read_table(args.local_file)
            dataset = Dataset(table.replace_schema_metadata(None))
        else:
            dataset = load_dataset(fmt[args.local_file.suffix.lower()], data_files=str(args.local_file), split="train")
        raw_hash = hashlib.sha256(args.local_file.read_bytes()).hexdigest()
        acquisition = "local snapshot"
    else:
        from huggingface_hub import HfApi
        revision = HfApi().dataset_info(PRIMARY, revision=revision, token=False).sha
        dataset = load_dataset(PRIMARY, revision=revision, split="train", token=False)
        raw_hash = None
        acquisition = "Hugging Face Datasets"
    print(f"Observed columns: {dataset.features}")
    rows, audit, issues = clean(dataset)
    if not rows:
        raise ValueError("No valid rows survived dataset validation.")
    splits = split_rows(rows)
    root = args.output
    existing = root / "splits" / "test_locked.csv"
    if existing.exists() and not args.replace_lock:
        raise ValueError("Locked split already exists. Use a new --output or explicitly pass --replace-lock.")
    data_hash = write_csv(root / "processed" / "ielts_task2_clean.csv", rows)
    split_info = {}
    for name, essays in splits.items():
        split_info[name] = {
            "count": len(essays), "bands": distribution(essays),
            "prompt_groups": len({row["prompt_group"] for row in essays}),
            "sha256": write_csv(root / "splits" / f"{name}.csv", essays),
        }
    manifest = {
        "dataset": PRIMARY, "revision": revision, "acquisition": acquisition,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "raw_sha256": raw_hash,
        "dataset_sha256": data_hash, "label_provenance": PROVENANCE, "license_reported": "CC BY 4.0",
        "seed": SEED, "near_duplicate_jaccard": NEAR_THRESHOLD, "minimum_words": MIN_WORDS,
        "band_distribution": distribution(rows),
        "word_counts": {"min": min(row["word_count"] for row in rows),
                        "median": median(row["word_count"] for row in rows),
                        "max": max(row["word_count"] for row in rows)},
        "splits": split_info, **audit,
    }
    (root / "processed" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "processed" / "audit_issues.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in issues), encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Download, audit and split the primary Writing9 corpus")
    parser.add_argument("--revision", help="Hugging Face commit SHA. Record this for local imports when known.")
    parser.add_argument("--local-file", type=Path, help="Use a previously downloaded parquet, CSV or JSON(L) export")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--replace-lock", action="store_true")
    args = parser.parse_args()
    try:
        prepare(args)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        parser.exit(1, f"Dataset preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
