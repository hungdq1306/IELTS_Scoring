"""Offline evaluation; draft annotations never become ground truth implicitly."""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from .extractor import ROOT, VERSION, read_jsonl
from .schemas import GoldRecord

MONTHS = {name: str(i) for i, pair in enumerate((('jan', 'january'), ('feb', 'february'),
    ('mar', 'march'), ('apr', 'april'), ('may', 'may'), ('jun', 'june'), ('jul', 'july'),
    ('aug', 'august'), ('sep', 'september'), ('oct', 'october'), ('nov', 'november'),
    ('dec', 'december')), 1) for name in pair}


def canonical(value):
    value = re.sub(r"[^\w]+", " ", str(value).casefold()).strip()
    return MONTHS.get(value, value)


def canonical_unit(value):
    value = str(value).strip().casefold()
    return {"percent": "%", "percentage": "%", "per cent": "%", "degrees celsius": "celsius",
        "°c": "celsius", "c": "celsius", "litres": "liters", "litre": "liters", "millions": "million", "thousands": "thousand"}.get(value, value)


def flatten(tables, explicit):
    cells = defaultdict(list)
    unknown = 0
    for table in tables:
        columns = table["columns"]
        for row in table["rows"]:
            for i, column in enumerate(columns):
                value = row["values"][i] if i < len(row["values"]) else None
                if value is None:
                    unknown += 1
                    continue
                label = row["raw_labels"][i] if i < len(row["raw_labels"]) else ""
                labeled = not label.strip().startswith("~") and (bool(label.strip()) or explicit)
                key = (canonical(table["table_id"]), canonical(row["series_name"]), canonical(column))
                cells[key].append((float(value), bool(labeled), canonical_unit(table["unit"])))
    return cells, unknown


def ratio(a, b):
    return 100 * a / b if b else None


def evaluate(gold_rows, result_rows):
    verified = []
    for raw in gold_rows:
        gold = GoldRecord.model_validate(raw)
        if gold.verification_status != "verified":
            continue
        if not gold.reviewed_by or not gold.reviewed_at or gold.has_explicit_labels is None or gold.flawed_or_low_confidence is None:
            raise ValueError(f"Verified record {gold.image_hash} needs reviewer, date, explicit-label flag and routing-safety annotation")
        if gold.visual_category.startswith("chart") and not gold.numeric_tables:
            raise ValueError("Verified numeric gold record has no tables")
        if gold.visual_category in ("map", "process") and not gold.spatial_or_process_steps:
            raise ValueError("Verified diagram gold record has no steps")
        if gold.visual_category == "mixed" and not (gold.numeric_tables or gold.spatial_or_process_steps):
            raise ValueError("Verified mixed gold record has no panels")
        for table in gold.numeric_tables:
            if not table.rows or not table.columns or any(len(row.values) != len(table.columns) or
                    len(row.raw_labels) != len(table.columns) for row in table.rows):
                raise ValueError("Malformed verified gold grid")
        verified.append(gold)
    if not verified:
        raise ValueError("No human-verified gold records. Review gold_template.jsonl; drafts cannot produce accuracy metrics.")
    if len({g.image_hash for g in verified}) != len(verified):
        raise ValueError("Duplicate gold image hashes")
    results = {r["image_hash"]: r for r in result_rows}
    totals = dict(gold_cells=0, predicted_cells=0, matched_gold_cells=0, correct_numeric_cells=0,
        exact_numeric_cells=0, unknown_gold_cells=0, flawed_items=0, caught_flawed_items=0)
    errors = []
    per_image = []
    for gold in verified:
        result = results.get(gold.image_hash)
        predicted = result["extraction"]["numeric_tables"] if result else []
        gcells, unknown = flatten([t.model_dump() for t in gold.numeric_tables], gold.has_explicit_labels)
        pcells, _ = flatten(predicted, result["extraction"]["has_explicit_labels"] if result else False)
        if any(len(v) != 1 for v in gcells.values()):
            raise ValueError("Duplicate semantic cell keys in gold")
        matched = correct = exact = 0
        local_errors = []
        for key, entries in gcells.items():
            if key not in pcells or len(pcells[key]) != 1:
                continue
            expected, labeled, gold_unit = entries[0]
            actual, _, unit = pcells[key][0]
            matched += 1
            equal = unit == gold_unit and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
            tolerance = 0 if labeled else .02 * abs(expected)
            within = unit == gold_unit and abs(actual - expected) <= tolerance + 1e-9
            exact += equal
            correct += within
            if unit == gold_unit and expected != 0:
                local_errors.append(abs(actual - expected) / abs(expected) * 100)
        predicted_count = sum(len(v) for v in pcells.values())
        totals["gold_cells"] += len(gcells)
        totals["predicted_cells"] += predicted_count
        totals["matched_gold_cells"] += matched
        totals["correct_numeric_cells"] += correct
        totals["exact_numeric_cells"] += exact
        totals["unknown_gold_cells"] += unknown
        totals["flawed_items"] += bool(gold.flawed_or_low_confidence)
        caught = bool(gold.flawed_or_low_confidence and result and result["routing_status"] == "needs_user_check")
        totals["caught_flawed_items"] += caught
        errors.extend(local_errors)
        per_image.append(dict(image_hash=gold.image_hash, prediction_available=result is not None,
            gold_cells=len(gcells), predicted_cells=predicted_count, matched_cells=matched, correct_numeric_cells=correct,
            cell_recall_pct=ratio(matched, len(gcells)), numeric_match_pct=ratio(correct, matched),
            missing_keys=[list(k) for k in gcells if k not in pcells or len(pcells[k]) != 1],
            extra_keys=[list(k) for k in pcells if k not in gcells], routing_safety_caught=caught))
    precision = ratio(totals["correct_numeric_cells"], totals["predicted_cells"])
    recall = ratio(totals["correct_numeric_cells"], totals["gold_cells"])
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else (0 if precision == 0 or recall == 0 else None)
    return dict(verified_images=len(verified), ignored_draft_images=len(gold_rows)-len(verified), **totals,
        cell_precision_pct=ratio(totals["matched_gold_cells"], totals["predicted_cells"]),
        cell_recall_pct=ratio(totals["matched_gold_cells"], totals["gold_cells"]),
        numeric_exact_match_pct=ratio(totals["exact_numeric_cells"], totals["matched_gold_cells"]),
        numeric_tolerance_match_pct=ratio(totals["correct_numeric_cells"], totals["matched_gold_cells"]),
        numeric_precision_pct=precision, numeric_recall_pct=recall, numeric_f1_pct=f1,
        numeric_mape_pct=sum(errors)/len(errors) if errors else None, mape_cell_count=len(errors),
        routing_safety_pct=ratio(totals["caught_flawed_items"], totals["flawed_items"]),
        definitions=dict(alignment="Stable visual panel table_id + canonical series + column; duplicate prediction keys cannot match; units must agree for numeric correctness.",
            tolerance="Exact numeric match for labeled cells; unlabeled +/-2% relative to gold value. Gold zero requires exact zero.",
            coverage="Presence of a non-null unambiguous cell, independent of numeric correctness; unknown gold values excluded and counted.",
            mape="Matched same-unit, nonzero-gold cells only. Never interpretable without coverage.",
            routing="Human flawed_or_low_confidence positives routed needs_user_check / all annotated positives, including missing predictions."),
        per_image=per_image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-file", type=Path, default=ROOT / "gold_set/verified_gold.jsonl")
    parser.add_argument("--results-file", type=Path, default=ROOT / "outputs/v2_exhaustive_sanity/extraction_results.jsonl")
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--output-file", type=Path, default=ROOT / "outputs/v2_exhaustive_sanity/gold_evaluation.json")
    args = parser.parse_args()
    if not args.gold_file.exists():
        parser.error("Verified gold file missing; only a draft template is available. No accuracy is reported.")
    results = [r for r in read_jsonl(args.results_file) if r.get("pipeline_version") == VERSION and r.get("model") == args.model]
    report = evaluate(read_jsonl(args.gold_file), results)
    report.update(model=args.model, pipeline_version=VERSION)
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("per_image", "definitions")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
