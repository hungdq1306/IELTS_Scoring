"""Lossless essay views and allowlisted, criterion-only anchor projection."""
import copy
import re
from app.grading.schemas import CRITERIA, Scores, word_count

PAYLOAD_VERSION = "single-essay-paragraphs-v1"
PARAGRAPH_SEPARATOR = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")


def paragraph_spans(essay):
    spans, start = [], 0
    for match in PARAGRAPH_SEPARATOR.finditer(essay):
        if essay[start:match.start()].strip():
            spans.append({"id": f"p{len(spans)+1}", "start": start, "end": match.start()})
        start = match.end()
    if essay[start:].strip():
        spans.append({"id": f"p{len(spans)+1}", "start": start, "end": len(essay)})
    return spans


def paragraph_metadata(essay, metadata=None):
    supplied = metadata or {}
    spans = supplied.get("paragraph_spans")
    verified = supplied.get("paragraph_boundary_verified")
    if spans is not None:
        previous = 0
        for index, span in enumerate(spans, 1):
            if (span["id"] != f"p{index}" or not 0 <= previous <= span["start"] < span["end"] <= len(essay)
                    or essay[previous:span["start"]].strip()):
                raise ValueError("Invalid or non-lossless paragraph spans")
            previous = span["end"]
        if essay[previous:].strip():
            raise ValueError("Paragraph spans omit essay text")
    else:
        spans = paragraph_spans(essay)
    if verified is None:
        verified = bool(PARAGRAPH_SEPARATOR.search(essay))
    return {"word_count": word_count(essay), "paragraph_count": len(spans),
            "paragraph_boundary_verified": bool(verified), "paragraph_spans": spans}


def essay_view(essay, metadata=None):
    meta = paragraph_metadata(essay, metadata)
    if meta["paragraph_boundary_verified"]:
        rendered = "\n\n".join(f"[{s['id']}]\n{essay[s['start']:s['end']]}" for s in meta["paragraph_spans"])
    else:
        # Unknown boundaries are never guessed from sentence/discourse markers.
        rendered = essay
    return rendered, {k: v for k, v in meta.items() if k != "paragraph_spans"}


def target_payload(prompt, essay, metadata=None):
    rendered, meta = essay_view(essay, metadata)
    return {"prompt": prompt, "student_essay": rendered, "metadata": meta}


def project_anchor(example):
    """Always start from raw stored text; never re-render an already projected view."""
    essay = example.get("student_essay", example.get("essay", example.get("student_essay_excerpt", "")))
    rendered, metadata = essay_view(essay, example.get("metadata", example))
    scores = example["scores"]
    result = {"question": example.get("question", example.get("prompt")),
              "student_essay": rendered, "scores": Scores(**{c: scores[c] for c in CRITERIA if c in scores}).model_dump(),
              "metadata": metadata,
              "provenance": {"score_source": example.get("score_source", example.get("label_provenance", example.get("source", "unverified"))),
                             "independently_verified": bool(example.get("score_provenance", {}).get("independently_verified")
                                or example.get("label_provenance") == "explicit_lecturer_annotation")}}
    if example.get("prompt_verified") is False:
        result["prompt_verified"] = False
    # Never forward free-form legacy cues or unverified teacher/AI reasoning.
    verified = result['provenance']['independently_verified']
    feedback = example.get("feedback_by_criterion")
    if verified and feedback:
        result["feedback_by_criterion"] = {
            c: {k: copy.deepcopy(v) for k, v in feedback[c].items()
                if k in {"score", "summary", "comments", "edits"}}
            for c in CRITERIA if c in feedback}
    return result


def transform_essay(essay, transform, metadata=None):
    """Transform text while preserving verified logical boundaries and updating offsets."""
    meta = paragraph_metadata(essay, metadata)
    parts, spans, previous, length = [], [], 0, 0
    for span in meta['paragraph_spans']:
        gap = transform(essay[previous:span['start']])
        body = transform(essay[span['start']:span['end']])
        parts.extend((gap, body))
        length += len(gap)
        spans.append({'id': span['id'], 'start': length, 'end': length + len(body)})
        length += len(body)
        previous = span['end']
    parts.append(transform(essay[previous:]))
    rendered = ''.join(parts)
    meta.update(paragraph_spans=spans, word_count=word_count(rendered))
    return rendered, meta
