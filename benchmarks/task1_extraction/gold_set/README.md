# Human review workflow

`gold_template.jsonl` contains 20 deterministic, balanced draft records: four per
source category, selected with seed 42. The 20 sampled hashes currently do not
overlap the ten smoke-test images; that does not make them independently verified.
Images remain at their normalized `image_path`; no duplicate image copies needed.
Generated and verified JSONL files are ignored by Git to preserve local annotations.

Inspect each image directly and fill every numeric cell and literal diagram step.
Keep `table_id` in top-to-bottom / left-to-right panel order (`t_01`, `t_02`, ...),
series names and column labels matching the visual axes. Preserve source errors;
record arithmetic anomalies in `review_notes` rather than silently correcting them.
Use numeric units as shown in the source; do not rescale values without changing units.
For unlabeled cells, prefix raw_labels with `~` and document interpolation. The evaluator
uses exact numeric matching for printed labels and +/-2% relative tolerance for
unlabeled cells (not +/-2 percentage points); a zero gold value requires exact zero.

After human review of a complete record:

1. Set `verification_status` to `verified` and fill `reviewed_by` and `reviewed_at`.
2. Set `has_explicit_labels` appropriately and annotate `flawed_or_low_confidence`
   from the image itself (unreadable/axis-estimated/contradictory values, etc.).
3. Save reviewed records to `verified_gold.jsonl`; keep unrevised drafts as drafts.
4. Run `python -m benchmarks.task1_extraction.eval_gold` (no LLM API calls).
   Use `--results-file` if evaluating a separate extraction run for the gold images.

Drafts are excluded from evaluation. If no verified records exist, evaluation fails
clearly and produces no claimed accuracy result. A reviewer/date marker is a
provenance declaration supplied by the reviewer, not automated proof of expertise.

Cell recall measures semantic key coverage, not number correctness. Numeric match
is reported over aligned cells, with precision/recall/F1 penalizing missing/extra
cells as well. MAPE excludes zero-gold and unit-incompatible cells and reports its
denominator. Routing safety uses independently annotated flawed/uncertain positives;
missing predictions count as not caught. No-positive denominators are null, not 100%.
Diagram semantic correctness still requires expert review; numeric metrics do not
measure whether a map transformation or process action is correctly understood.

Re-export protects an existing template. Use --overwrite-gold-template only if you
intend to replace local drafts. --gold-draft-results can prefill matching current-
version extractions; these remain drafts and do not bypass human verification.

To extract exactly the sampled images rather than the first 20 dataset images:

```cmd
benchmarks\task1_extraction\run_all.cmd --source github --limit 0 --select-hashes-from benchmarks/task1_extraction/gold_set/gold_template.jsonl --output-dir benchmarks/task1_extraction/outputs/gold_sample
.venv\Scripts\python.exe -m benchmarks.task1_extraction.eval_gold --results-file benchmarks/task1_extraction/outputs/gold_sample/extraction_results.jsonl --output-file benchmarks/task1_extraction/outputs/gold_sample/gold_evaluation.json
```

Extraction may use draft hash selection; evaluation still requires human-verified
records. --select-hashes-from rejects unknown/empty selections and applies --limit
after selection. Benchmark and audit always share the same selected prompt set.
