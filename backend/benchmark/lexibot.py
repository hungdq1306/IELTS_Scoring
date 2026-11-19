"""Normalize Lexibot DOCX exports and compare a completed grading run."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.config import ROOT
from app.grading.aspects import ASPECT_LABELS, LENGTH_ASPECT
from app.grading.schemas import GradeRequest, word_count
from benchmark import store
from benchmark.datasets import normalize, parse_band, write_csv
from benchmark.metrics import score_metrics

PROVENANCE = "Lexibot estimates transcribed from supplied DOCX files; agreement with another system, without examiner verification."
NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SCORE = re.compile(r"^(.+?):\s*([0-9]+(?:\.[05])?)\s*\.?$")
CRITERIA = {
    "Task Response (TR)": "tr", "Coherence & Cohesion (CC)": "cc",
    "Lexical Resource (LR)": "lr", "Grammatical Range & Accuracy (GRA)": "gra",
}
SOURCE = ROOT / "data" / "lexibot"
OUTPUT = ROOT / "data" / "processed" / "lexibot"


def paragraphs_from_docx(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(NAMESPACE + "body")
    paragraphs = []
    for node in body.iter(NAMESPACE + "p"):
        value = "".join(
            (part.text or "") if part.tag == NAMESPACE + "t" else
            "\n" if part.tag == NAMESPACE + "br" else "\t" if part.tag == NAMESPACE + "tab" else ""
            for part in node.iter()
        ).strip()
        if value:
            paragraphs.append(value)
    return paragraphs


def parse_docx(path):
    lines = paragraphs_from_docx(path)
    try:
        headings = [lines.index(title) for title in
                    ("Topic", "Your Response", "Correct Grammar Errors", "Estimated Band Score.")]
        topic, response, corrected, scores = headings
        overall = next(i for i in range(scores + 1, len(lines))
                       if lines[i].startswith("Est. Overall Band Score:"))
        if sorted(headings) != headings:
            raise ValueError("unexpected heading order")
        prompt = "\n".join(lines[topic + 1:response])
        original = lines[response + 1:corrected]
        request = GradeRequest(prompt=prompt, essay="\n\n".join(original))
        revised = lines[corrected + 1:scores]
        no_critical_errors = revised == ["Good job! No critical grammar errors found."]
        diagnostic, criteria, feedback = {}, {}, defaultdict(list)
        current = None
        for line in lines[scores + 1:overall + 1]:
            match = SCORE.fullmatch(line)
            label = match.group(1) if match else None
            if label in CRITERIA:
                current = CRITERIA[label]
                if current in criteria:
                    raise ValueError(f"duplicate criterion: {label}")
                criteria[current] = parse_band(match.group(2))
            elif label == "Est. Overall Band Score":
                criteria["overall"] = parse_band(match.group(2))
            elif label in (*ASPECT_LABELS, LENGTH_ASPECT):
                if label in diagnostic:
                    raise ValueError(f"duplicate aspect: {label}")
                diagnostic[label] = parse_band(match.group(2))
            elif current:
                feedback[current].append(line)
        if (set(criteria) != {"overall", *CRITERIA.values()}
                or set(feedback) != set(CRITERIA.values())
                or set(diagnostic) != {*ASPECT_LABELS, LENGTH_ASPECT}):
            raise ValueError("missing scoring or feedback fields")
        return {
            "essay_id": path.name.split("_", 1)[0],
            "source_file": path.name,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "prompt": request.prompt,
            "essay": request.essay,
            "paragraphs": original,
            "word_count": word_count(request.essay),
            "reference": {
                "bands": criteria, "diagnostic_scores": diagnostic,
                "criterion_feedback": {key: "\n".join(value) for key, value in feedback.items()},
                "correction_status": "no_critical_errors_reported" if no_critical_errors else "revision_supplied" if revised else "unavailable",
                "revised_paragraphs": revised if revised and not no_critical_errors else None,
                "paragraph_feedback": ({"paragraph_number": 1, "coverage": "opening_only",
                                        "source_lines": lines[overall + 1:]}
                                       if "OPENING STATEMENT" in lines[overall + 1:] else None),
                "other_feedback": (lines[overall + 1:] or None) if "OPENING STATEMENT" not in lines[overall + 1:] else None,
            },
        }
    except (StopIteration, ValueError) as exc:
        raise ValueError(f"{path.name}: cannot normalize source: {exc}") from exc


def prepare(source, output):
    records = [parse_docx(path) for path in sorted(source.glob("lexi*_trimmed.docx"))]
    if not records or len({r["essay_id"] for r in records}) != len(records):
        raise ValueError("Expected distinct Lexibot source documents.")
    if len({normalize(r["essay"]) for r in records}) != len(records):
        raise ValueError("Duplicate Lexibot essay text found.")
    output.mkdir(parents=True, exist_ok=True)
    reference_path = output / "lexibot.references.jsonl"
    reference_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    csv_hash = write_csv(output / "lexibot.csv", [
        {
            "essay_id": r["essay_id"], "prompt": r["prompt"], "essay": r["essay"],
            "source_dataset": "Lexibot", "topic": "", "word_count": r["word_count"],
            "prompt_group": hashlib.sha256(normalize(r["prompt"]).encode()).hexdigest()[:16],
            "quality_flags": "",
            **{f"gold_{key}": value for key, value in r["reference"]["bands"].items()},
        }
        for r in records
    ])
    manifest = {
        "revision": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        "csv_sha256": csv_hash, "label_provenance": PROVENANCE,
        "essays": len(records),
        "source_files": {r["source_file"]: r["source_sha256"] for r in records},
        "revisions_supplied": sum(r["reference"]["revised_paragraphs"] is not None for r in records),
        "paragraph_feedback_supplied": sum(r["reference"]["paragraph_feedback"] is not None for r in records),
    }
    (output / "lexibot.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def compare(database, source):
    meta, rows, _ = store.read(database)
    references_path = source / "lexibot.references.jsonl"
    raw = references_path.read_bytes()
    if meta["dataset"] != "Lexibot" or meta["dataset_revision"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("The run did not use this exact Lexibot reference snapshot.")
    references = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    predicted_by_id = {row["essay_id"]: row for row in rows}
    facet_pairs = defaultdict(list)
    cases = []
    for reference in references:
        ref = reference["reference"]
        row = predicted_by_id.get(reference["essay_id"], {})
        prediction = row.get("prediction")
        if row and (row["gold"] != ref["bands"] or row["prompt"] != reference["prompt"] or row["essay"] != reference["essay"]):
            raise ValueError(f"Input or reference mismatch for {reference['essay_id']}.")
        for review in (prediction or {}).get("aspect_reviews", []):
            facet_pairs[review["aspect"]].append((ref["diagnostic_scores"][review["aspect"]], review["score"]))
        cases.append({
            "essay_id": reference["essay_id"], "status": row.get("status", "not_attempted"),
            "prompt": reference["prompt"], "essay": reference["essay"],
            "lexibot": ref, "prediction": prediction,
            "feedback_coverage": {
                "essay_paragraphs": len(reference["paragraphs"]),
                "gemini_paragraph_reviews": len(prediction.get("paragraph_reviews", [])) if prediction else None,
                "gemini_diagnostics": len(prediction.get("aspect_reviews", [])) if prediction else None,
                "gemini_grounded_grammar_edits": len(prediction.get("grammar_corrections", [])) if prediction else None,
                "gemini_grounded_language_suggestions": len(prediction.get("language_suggestions", [])) if prediction else None,
            },
            "opening_review_available_for_manual_comparison": bool(
                ref["paragraph_feedback"] and prediction and
                any(p["paragraph_number"] == 1 for p in prediction.get("paragraph_reviews", []))
            ),
        })
    return {
        "run_id": meta["run_id"], "label_provenance": PROVENANCE,
        "aspect_agreement": {label: score_metrics(facet_pairs[label]) for label in ASPECT_LABELS},
        "word_count_diagnostic": "Lexibot score retained in reference; our feedback reports measured word count rather than a band.",
        "manual_feedback_review": [
            "Check whether each claimed problem occurs in the original paragraph.",
            "Check whether each proposed edit fixes the issue and preserves meaning.",
            "Check whether suggestions distinguish grammar errors from optional style changes.",
            "Check whether each criterion identifies specific strengths and actionable next steps.",
        ],
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
