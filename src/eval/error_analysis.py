"""Zero-cost error diagnosis on Baseline v0 Dev (173) and Examiner LOO-CV (13) logs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_error_analysis(
    dev_preds_path: Path = Path("artifacts/dataset_v1/baseline_v0/dev_live_predictions.jsonl"),
    loo_preds_path: Path = Path("artifacts/dataset_v1/baseline_v0/loo_live_predictions.jsonl"),
    out_md: Path = Path("artifacts/dataset_v1/baseline_v0/error_analysis_v0.md"),
) -> str:
    dev_rows = _load_jsonl(dev_preds_path)
    loo_rows = _load_jsonl(loo_preds_path)

    lines: list[str] = [
        "# Baseline v0 Error Analysis (Dev 173 + Examiner LOO-CV 13)",
        "",
        "## 1. Worst 5 Under-Scored Essays on CC (Dev)",
    ]
    cc_sorted = sorted(dev_rows, key=lambda r: (r["pred"]["cc"] - r["true"]["cc"], r["essay_id"]))
    for r in cc_sorted[:5]:
        err = r["pred"]["cc"] - r["true"]["cc"]
        cc_rat = r["rationale"]["criteria"]["coherence_cohesion"]
        lines.append(
            f"- `{r['essay_id']}` | True: `TR={r['true']['tr']}, CC={r['true']['cc']}, LR={r['true']['lr']}, GRA={r['true']['gra']}, OV={r['true']['overall']}` "
            f"→ Pred: `TR={r['pred']['tr']}, CC={r['pred']['cc']}, LR={r['pred']['lr']}, GRA={r['pred']['gra']}, OV={r['pred']['overall']}` "
            f"(**CC err = {err:+.1f}**)"
        )
        lines.append(f"  - *CC rationale:* {cc_rat}")

    lines.extend(["", "## 2. Worst 5 Under-Scored Essays on GRA (Dev)"])
    gra_sorted = sorted(dev_rows, key=lambda r: (r["pred"]["gra"] - r["true"]["gra"], r["essay_id"]))
    for r in gra_sorted[:5]:
        err = r["pred"]["gra"] - r["true"]["gra"]
        gra_rat = r["rationale"]["criteria"]["grammatical_range_accuracy"]
        lines.append(
            f"- `{r['essay_id']}` | True: `TR={r['true']['tr']}, CC={r['true']['cc']}, LR={r['true']['lr']}, GRA={r['true']['gra']}, OV={r['true']['overall']}` "
            f"→ Pred: `TR={r['pred']['tr']}, CC={r['pred']['cc']}, LR={r['pred']['lr']}, GRA={r['pred']['gra']}, OV={r['pred']['overall']}` "
            f"(**GRA err = {err:+.1f}**)"
        )
        lines.append(f"  - *GRA rationale:* {gra_rat}")

    lines.extend(["", "## 3. All 6 High-Band (8.5–9.0) Examiner Essays in LOO-CV"])
    high_loo = [r for r in loo_rows if r["true"]["overall"] >= 8.5]
    high_loo.sort(key=lambda r: r["target_essay_id"])
    for r in high_loo:
        t, p = r["true"], r["pred"]
        cr = r["rationale"]["criteria"]
        lines.append(
            f"- `{r['target_essay_id']}` | True: `TR={t['tr']}, CC={t['cc']}, LR={t['lr']}, GRA={t['gra']}, OV={t['overall']}` "
            f"→ Pred: `TR={p['tr']}, CC={p['cc']}, LR={p['lr']}, GRA={p['gra']}, OV={p['overall']}` "
            f"(**OV err = {p['overall'] - t['overall']:+.1f}**)"
        )
        lines.append(f"  - *Brief:* {r['rationale']['brief']}")
        lines.append(f"  - *CC:* {cr['coherence_cohesion']}")
        lines.append(f"  - *GRA:* {cr['grammatical_range_accuracy']}")

    text = "\n".join(lines) + "\n"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(run_error_analysis())
