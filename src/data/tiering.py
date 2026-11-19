"""Data cleaning, IELTS score normalization, and quality tiering for Task 2 essays."""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

QualityTier = Literal["examiner_verified", "max2_half", "max3_half_only", "rejected"]
CRITERIA_KEYS = ("tr", "cc", "lr", "gra")

# Strict pattern for scraped website / HTML contamination (avoids false positives on essays about copyright law)
ARTIFACT_RE = re.compile(
    r"<[^>]+>|https?://|www\.|&nbsp;|&amp;|writing9|unauthorized\s+use|full\s+and\s+clear\s+credit\s+is\s+given",
    re.IGNORECASE,
)


def round_half(val: float | int | str | Decimal) -> float:
    """Round a numeric value to the nearest 0.5 increment using official IELTS ROUND_HALF_UP."""
    dec = val if isinstance(val, Decimal) else Decimal(str(val))
    half_units = (dec * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(half_units / Decimal("2"))


def compute_ielts_overall(tr: float, cc: float, lr: float, gra: float) -> float:
    """Compute official IELTS Writing Task 2 overall band (.25 -> .5, .75 -> +1.0)."""
    total = Decimal(str(tr)) + Decimal(str(cc)) + Decimal(str(lr)) + Decimal(str(gra))
    half_units = (total / Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(half_units / Decimal("2"))


def parse_half_band(raw: Any) -> float | None:
    """Parse and normalize a criterion band score to [0.0, 9.0] in 0.5 increments."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        dec = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    val = round_half(dec)
    if val < 0.0 or val > 9.0:
        return None
    return val


def detect_artifact(prompt: str, essay: str) -> str | None:
    """Return an explicit reason string if prompt/essay is missing or contaminated."""
    p = (prompt or "").strip()
    e = (essay or "").strip()
    if not p:
        return "missing_prompt"
    if not e:
        return "missing_essay"
    if len(e.split()) < 30:
        return "corrupted_short_essay"
    m_prompt = ARTIFACT_RE.search(p)
    if m_prompt:
        return f"scraped_artifact_in_prompt:{m_prompt.group(0)}"
    m_essay = ARTIFACT_RE.search(e)
    if m_essay:
        return f"scraped_artifact_in_essay:{m_essay.group(0)}"
    return None


class EssayRecord(BaseModel):
    """Canonical schema for an IELTS Writing Task 2 dataset record."""

    model_config = ConfigDict(extra="forbid")

    essay_id: str
    prompt: str
    essay: str
    prompt_cluster_id: str | None = None
    quality_tier: QualityTier
    tr: float = Field(..., ge=0.0, le=9.0)
    cc: float = Field(..., ge=0.0, le=9.0)
    lr: float = Field(..., ge=0.0, le=9.0)
    gra: float = Field(..., ge=0.0, le=9.0)
    overall: float = Field(..., ge=0.0, le=9.0)
    word_count: int = Field(..., ge=1)
    source: str
    examiner_feedback: dict[str, Any] | list[Any] | str | None = None
    r1_scores: dict[str, float] | None = None
    r2_scores: dict[str, float] | None = None
    rater_diffs: dict[str, float] | None = None

    @field_validator("tr", "cc", "lr", "gra", "overall")
    @classmethod
    def _validate_half_increment(cls, v: float) -> float:
        if round(v * 2) != v * 2:
            raise ValueError(f"Band score must be in 0.5 increments, got {v}")
        return float(v)


class DroppedRecord(BaseModel):
    """Audit record for any excluded or rejected essay."""

    model_config = ConfigDict(extra="forbid")

    essay_id: str
    source: str
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


def _load_examiner_verified(config: dict[str, Any], root: Path) -> tuple[list[EssayRecord], list[DroppedRecord]]:
    records: list[EssayRecord] = []
    dropped: list[DroppedRecord] = []
    inputs = config["inputs"]
    cm = config["column_mappings"]

    # 1. Load 7 detailed lecturer-graded essays (fs7_v1.json)
    fs7_path = root / inputs["examiner_fs7_json"]
    fs7_cfg = cm["examiner_fs7"]
    fs7_payload = json.loads(fs7_path.read_text(encoding="utf-8"))
    for item in fs7_payload.get("examples", []):
        eid = str(item.get(fs7_cfg["id"], "")).strip()
        prompt = str(item.get(fs7_cfg["prompt"], "")).strip()
        essay = str(item.get(fs7_cfg["essay"], "")).strip()
        artifact = detect_artifact(prompt, essay)
        if artifact:
            dropped.append(DroppedRecord(essay_id=eid, source="examiner_fs7", reason=artifact))
            continue
        scores_obj = item.get(fs7_cfg["scores_obj"], {})
        parsed = {k: parse_half_band(scores_obj.get(v)) for k, v in fs7_cfg["criteria"].items()}
        if any(val is None for val in parsed.values()):
            dropped.append(DroppedRecord(essay_id=eid, source="examiner_fs7", reason="missing_criterion_score"))
            continue
        ov = compute_ielts_overall(parsed["tr"], parsed["cc"], parsed["lr"], parsed["gra"])
        records.append(
            EssayRecord(
                essay_id=eid,
                prompt=prompt,
                essay=essay,
                quality_tier="examiner_verified",
                tr=parsed["tr"],
                cc=parsed["cc"],
                lr=parsed["lr"],
                gra=parsed["gra"],
                overall=ov,
                word_count=len(essay.split()),
                source="examiner_fs7",
                examiner_feedback=item.get(fs7_cfg["feedback"]),
            )
        )

    # 2. Load 6 verified high-band essays (supplemental/essays.jsonl)
    supp_path = root / inputs["examiner_supplemental_jsonl"]
    supp_cfg = cm["examiner_supplemental"]
    with supp_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            eid = str(item.get(supp_cfg["id"], "")).strip()
            prompt = str(item.get(supp_cfg["prompt"], "")).strip()
            essay = str(item.get(supp_cfg["essay"], "")).strip()
            artifact = detect_artifact(prompt, essay)
            if artifact:
                dropped.append(DroppedRecord(essay_id=eid, source="examiner_supplemental", reason=artifact))
                continue
            scores_obj = item.get(supp_cfg["scores_obj"], {})
            parsed = {k: parse_half_band(scores_obj.get(v)) for k, v in supp_cfg["criteria"].items()}
            if any(val is None for val in parsed.values()):
                dropped.append(
                    DroppedRecord(essay_id=eid, source="examiner_supplemental", reason="missing_criterion_score")
                )
                continue
            ov = compute_ielts_overall(parsed["tr"], parsed["cc"], parsed["lr"], parsed["gra"])
            feedback = item.get(supp_cfg["feedback"]) or None
            records.append(
                EssayRecord(
                    essay_id=eid,
                    prompt=prompt,
                    essay=essay,
                    quality_tier="examiner_verified",
                    tr=parsed["tr"],
                    cc=parsed["cc"],
                    lr=parsed["lr"],
                    gra=parsed["gra"],
                    overall=ov,
                    word_count=len(essay.split()),
                    source="examiner_supplemental",
                    examiner_feedback=feedback,
                )
            )

    records.sort(key=lambda r: r.essay_id)
    return records, dropped


def _load_dual_rater_tiered(
    config: dict[str, Any], root: Path
) -> tuple[list[EssayRecord], list[DroppedRecord], dict[str, int]]:
    records: list[EssayRecord] = []
    dropped: list[DroppedRecord] = []
    counts = {"total_raw": 0, "max2_half": 0, "max3_half_only": 0, "rejected": 0, "dropped_clean": 0}

    inputs = config["inputs"]
    cm = config["column_mappings"]
    r1_cfg = cm["rater1_csv"]
    r2_cfg = cm["rater2_json"]
    max_spread = float(config.get("max_criterion_spread", 2.0))

    r2_raw = json.loads((root / inputs["rater2_json"]).read_text(encoding="utf-8"))
    r2_records = r2_raw[r2_cfg["records_key"]] if isinstance(r2_raw, dict) and r2_cfg["records_key"] in r2_raw else r2_raw

    seen_ids: set[str] = set()
    with (root / inputs["rater1_csv"]).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            counts["total_raw"] += 1
            eid = str(row.get(r1_cfg["id"], "")).strip()
            if not eid:
                counts["dropped_clean"] += 1
                dropped.append(DroppedRecord(essay_id="<missing>", source="dual_rater", reason="missing_essay_id"))
                continue
            if eid in seen_ids:
                counts["dropped_clean"] += 1
                dropped.append(DroppedRecord(essay_id=eid, source="dual_rater", reason="duplicate_essay_id"))
                continue
            seen_ids.add(eid)

            prompt = str(row.get(r1_cfg["prompt"], "") or "").strip()
            essay = str(row.get(r1_cfg["essay"], "") or "").strip()
            artifact = detect_artifact(prompt, essay)
            if artifact:
                counts["dropped_clean"] += 1
                dropped.append(DroppedRecord(essay_id=eid, source="dual_rater", reason=artifact))
                continue

            if eid not in r2_records:
                counts["dropped_clean"] += 1
                dropped.append(DroppedRecord(essay_id=eid, source="dual_rater", reason="missing_rater2_record"))
                continue

            r1_parsed = {k: parse_half_band(row.get(col)) for k, col in r1_cfg["criteria"].items()}
            r2_obj = r2_records[eid]
            r2_parsed = {k: parse_half_band(r2_obj.get(col)) for k, col in r2_cfg["criteria"].items()}

            if any(v is None for v in r1_parsed.values()) or any(v is None for v in r2_parsed.values()):
                counts["dropped_clean"] += 1
                dropped.append(
                    DroppedRecord(
                        essay_id=eid,
                        source="dual_rater",
                        reason="missing_or_invalid_criterion_score",
                        details={"r1": r1_parsed, "r2": r2_parsed},
                    )
                )
                continue

            diffs = {k: round(abs(r1_parsed[k] - r2_parsed[k]), 2) for k in CRITERIA_KEYS}
            max_diff = max(diffs.values())
            half_count = sum(1 for d in diffs.values() if d == 0.5)

            if max_diff <= 0.5 and half_count <= 2:
                tier: QualityTier = "max2_half"
            elif max_diff <= 0.5 and half_count == 3:
                tier = "max3_half_only"
            else:
                tier = "rejected"

            # Gold aggregation: midpoint rounded half-up (matching existing compare_raters.py convention)
            agg = {
                k: round_half((Decimal(str(r1_parsed[k])) + Decimal(str(r2_parsed[k]))) / Decimal("2"))
                for k in CRITERIA_KEYS
            }
            ov = compute_ielts_overall(agg["tr"], agg["cc"], agg["lr"], agg["gra"])
            spread = max(agg.values()) - min(agg.values())

            if tier == "rejected":
                counts["rejected"] += 1
                dropped.append(
                    DroppedRecord(
                        essay_id=eid,
                        source="dual_rater",
                        reason=f"tier_rejected(max_diff={max_diff:g},half_count={half_count})",
                        details={"r1": r1_parsed, "r2": r2_parsed, "diffs": diffs},
                    )
                )
                continue

            if spread > max_spread:
                counts["dropped_clean"] += 1
                dropped.append(
                    DroppedRecord(
                        essay_id=eid,
                        source="dual_rater",
                        reason=f"high_criterion_spread(spread={spread:g}>{max_spread:g})",
                        details={"tier": tier, "agg": agg},
                    )
                )
                continue

            counts[tier] += 1
            records.append(
                EssayRecord(
                    essay_id=eid,
                    prompt=prompt,
                    essay=essay,
                    quality_tier=tier,
                    tr=agg["tr"],
                    cc=agg["cc"],
                    lr=agg["lr"],
                    gra=agg["gra"],
                    overall=ov,
                    word_count=len(essay.split()),
                    source=f"writing9_dual_rater_{tier}",
                    examiner_feedback=None,
                    r1_scores=r1_parsed,
                    r2_scores=r2_parsed,
                    rater_diffs=diffs,
                )
            )

    records.sort(key=lambda r: r.essay_id)
    return records, dropped, counts


def load_and_tier_dataset(config: dict[str, Any], root: Path | None = None) -> tuple[list[EssayRecord], list[DroppedRecord], dict[str, Any]]:
    """Load, clean, normalize, and assign quality tiers to all examiner and dual-rater essays."""
    repo_root = root or Path.cwd()
    examiner_records, ex_dropped = _load_examiner_verified(config, repo_root)
    dr_records, dr_dropped, dr_counts = _load_dual_rater_tiered(config, repo_root)

    all_records = examiner_records + dr_records
    all_dropped = ex_dropped + dr_dropped
    summary = {
        "examiner_verified": len(examiner_records),
        "dual_rater_raw": dr_counts["total_raw"],
        "max2_half": dr_counts["max2_half"],
        "max3_half_only": dr_counts["max3_half_only"],
        "rejected": dr_counts["rejected"],
        "dropped_clean_or_outlier": dr_counts["dropped_clean"] + len(ex_dropped),
        "total_retained": len(all_records),
    }
    return all_records, all_dropped, summary
