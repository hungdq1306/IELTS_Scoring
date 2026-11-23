# Task 1 visual extraction benchmark

## Current exhaustive/sanity pipeline (version 3)

Default model: `gemini-3.1-flash-lite`; default concurrency: 2. New output defaults
to `outputs/v2_exhaustive_sanity/`. Historical version-2 output below is preserved
at `outputs/essayjudge_gemini_3_1_flash_lite/` and is never used as a schema-v3 cache.

```cmd
.venv\Scripts\python.exe -m benchmarks.task1_extraction.prepare_essayjudge --source github --export-gold-template 20
benchmarks\task1_extraction\run_all.cmd --source github --limit 10 --output-dir benchmarks/task1_extraction/outputs/v2_exhaustive_sanity
.venv\Scripts\python.exe -m benchmarks.task1_extraction.audit_consistency --limit 10 --skip-audit
.venv\Scripts\python.exe -m benchmarks.task1_extraction.eval_gold
```

The schema declares all numeric matrices before diagram elements, notes, overview
and model confidence. Null/unreadable cells and malformed grids are retained with
warnings instead of repaired or hidden. Complete declared grids alone cannot prove
that the model detected every axis label; compare against verified gold labels.
Arithmetic checks validate percentage partitions (>1.5 percentage-point difference)
and explicit total rows/columns (>1.5% relative difference). Sanity warnings force
confidence <=75 and needs_user_check. Uncertain numeric rows also prevent auto routing.
Maps/processes/mixed retain <=80 caps; unlabeled charts <=78; blurry <=60.

Five API attempts maximum, explicit HTTP 429/500/502/503/504 retries with exponential
backoff+jitter (base 2 s, cap 30 s), SDK retries disabled. Every attempt has status,
latency, backoff and known token usage. Failed attempts without provider usage make
`token_usage_complete=false`; `total_tokens_including_retries` is then a LOWER BOUND,
not an exact cost. Error checkpoints include the full failed-attempt telemetry.

Per-item timings: load JPEG, validate/reuse normalized JPEG (`t_normalize_ms`, no
re-encoding), extraction including retries, sanity and item total. Item total excludes
queue wait, preparation and silver audit. `run_summary.json` records invocation wall
time; `data/preparation_timings.json` records ingestion/normalization-group wall time;
audit checkpoints record `t_audit_ms`. Do not add cached-stage durations and call that
an end-to-end fresh-request latency. Historical timing observations below are v2.

All 121 unique images are tagged from official source metadata: chart_static 56,
chart_time_series 15, process 29, mixed 13, map 8. Source subtype counts are bar 30,
line 15, pie 9, table 17, flow 29, composite 13, map 8. Two map examples were visually
checked (student accommodation plan; museum 1998/2008); the overall scan is metadata-
based and is not independently adjudicated visual classification.

20-image `gold_set/gold_template.jsonl`: four drafts per category, deterministic seed
42, protected from overwrite. See [gold review workflow](gold_set/README.md). There
is no human-verified gold file yet, so no accuracy/F1/MAPE is claimed for real data.
Numeric evaluator and routing safety tests use clearly synthetic annotations only.

The HTML shows all matrices, copied raw labels, literal diagram steps, sanity
alerts, attempt counts, and stage timing. `--skip-audit` uses cached silver verdicts
or clearly marks not_run; `--allow-partial` renders failed extractions explicitly
and still exits nonzero. These flags never imply a completed gold evaluation.


Standalone experiment; no imports or changes to production `app.pilot:app`.
All commands run from the repository root. Requires Python 3.11+, Pillow,
Pydantic v2, google-genai, python-dotenv and datasets (available in `.venv`).
The existing repository requirements supply all except Pillow explicitly;
install missing dependencies with `python -m pip install -r benchmarks/task1_extraction/requirements.txt`, without changing production dependencies.

```cmd
benchmarks\task1_extraction\run_all.cmd --source github --limit 10
benchmarks\task1_extraction\run_all.cmd --limit 0 --model gemini-3.1-flash-lite --concurrency 3
benchmarks\task1_extraction\run_all.cmd --limit 5 --local-file path\to\essays.json
.venv\Scripts\python.exe -m unittest benchmarks.task1_extraction.test_pipeline -v
```

`GEMINI_API_KEY` is loaded from the environment or repository `.env`.
Hugging Face credentials, if required, use the existing datasets/HF configuration.
The scripts do not change security settings or write secrets to the repository.
`run_all.cmd` stops on the first failed stage and forwards arguments to all stages.
Individual stages run with `python -m benchmarks.task1_extraction.<module>`.
Use `--data-dir` and `--output-dir` to isolate experiments; normalized image paths
in the prompt manifest are absolute, so re-prepare after moving the workspace.

## Input and scoring

Default source mode is `auto`: try `EssayJudge/EssayJudge` on Hugging Face,
then fall back explicitly to the same dataset's official GitHub release
<https://github.com/jsu360/EssayJudge> on its `master` branch. The HF identifier
returned HTTP 401 / DatasetNotFoundError on 2026-11-23. The official CSV and
its linked prompt images are publicly accessible. Use `--source github` to
skip the failed HF lookup, or `--source huggingface` to disable fallback.
Custom `--dataset-name` failures never silently fall back.

The GitHub loader pins the CSV commit SHA, preserves its original GB18030 bytes,
and stores CSV/image SHA-256 checksums, original URLs, counts and the score
selection policy in `data/source/provenance.json`. Cached downloads are verified
on reuse. The raw image URLs in the official CSV point to the author's
`jsu360/MLLM-for-AES` repository; those bytes are retained locally with checksums.
Use `--local-file` for JSON/JSONL/Parquet containing images, essays and human scores.

Column names are matched case-insensitively with separators normalized.
Images can be PIL images, HF bytes/path objects, or paths relative to the local file.
Score selection prefers overall, then task achievement/response, then mean of
available score/band/ground-truth columns. The official CSV has ten human trait
columns and no overall score, so silver ranking uses their mean (not an IELTS band). Only supply human scores in these fields; model
predictions are not suitable silver-reference labels. Missing scores remain null;
ties retain the first essay. Data preparation visits every split and every row.

Images are EXIF-oriented, converted to RGB, downscaled only when wider than
1024 pixels, and encoded once as JPEG quality 85. SHA-256 identifies those exact
bytes. Equal normalized bytes are deduplicated; visually similar but differently
encoded source images are not guaranteed to collapse. Dataset counts are measured,
not forced to match the expected 1,054 essays / approximately 125 images.

## Routing and audit

Schema fields ground facts before confidence. Deterministic clarity/category/label
caps implement the supplied policy exactly. Unlabeled facts are flagged for review.
`auto_verified` is a policy label, not independently measured factual accuracy.
Silver essays are fallible consistency references, never input to extraction.
Audit verdicts do not establish extraction precision, recall or grading quality.

Extraction checkpoints are keyed by image hash, model and pipeline version.
Increment VERSION after changing extraction prompts/schema/routing. Audit cache
keys include the model, version, audit prompt, facts and reference essay. Successful
records are fsynced immediately; failures remain in extraction_errors.jsonl.
Malformed JSONL fails with the offending line number; it is never silently skipped.
Concurrency bounds in-flight requests. HTTP 429/503 retries use exponential backoff
with jitter (six attempts total); other errors remain visible. This is not a fixed
requests-per-minute quota. Latency includes retries; input/output tokens are recorded
separately. Provider thinking tokens may incur additional usage beyond output tokens.

Outputs and downloaded data are ignored by Git locally under this folder.
The HTML embeds images, escapes untrusted text, highlights review rows and supports
category filtering without a server or external assets. Do not publish private essays
without checking the source dataset terms.

## Verification on 2026-11-23

- Eight offline regression tests cover field order, 120 routing combinations,
  deterministic normalization, deduplication/silver ranking, malformed checkpoints,
  UTF-8, safe self-contained HTML rendering, 429 retry, checkpoint resume and audit caching.
- All Python modules compile on Python 3.11.
- The initial default command stopped at inaccessible Hugging Face source; the
  official-source loader below now resolves this.
- A separate five-image synthetic bar-chart fixture exercises local preparation.
  It is not EssayJudge and cannot measure quality on real IELTS visuals.
- `gemini-2.5-flash` returned HTTP 404 (unavailable to new users).
  The default is now `gemini-3.1-flash-lite`, as requested.
- `gemini-3.8-flash`: three recorded 504 errors before stopping the slow run.
- `gemini-3-flash-preview`: 2/5 synthetic images extracted; 3/5 returned 504.
  Both successful extractions were audited as consistent, and the portable report
  was generated at `outputs/synthetic_smoke/review_report.html` (65,017 bytes,
  two embedded JPEGs validated). This is a successful-subset report, not a 5/5 run.
  Resuming this subset selected 2 cached records with 0 pending API requests.
  Successful extraction p50 was 31,070 ms and p95 was 38,720 ms; these two samples
  do not establish real-data latency or extraction accuracy.

The original full-data benchmark was unverified at this stage. The synthetic
fixture, checkpoints and failed requests are retained locally under ignored
`data/` and `outputs/` folders. See the official-source reconnection below.

## Default-model update

`gemini-3.1-flash-lite` is now the default for extraction and audit.
Five of five synthetic prompt images extracted successfully. Checkpoints are in
`outputs/gemini_3_1_flash_lite_smoke/extraction_results.jsonl`.
The live audit was stopped after a prolonged wait without a completed audit record;
no new HTML report is claimed for this run. Resume the audit with the same model,
data directory and output directory. Eight offline tests and compilation passed.

## Official-source reconnection

The official release has been downloaded: 1,054 essays, 125 source URLs, 121 unique
raw image checksums and 121 normalized image hashes. Duplicate URLs/images reduce
the actual prompt count below the originally expected 125. Every prompt has a
silver-reference score (mean human trait score, range 2.9–4.9 for selected essays).
CSV revision: `2ac9ad7814bc0b43b865e37137a9b6c52aab7009`.
CSV SHA-256: `7998f78165f3b354f42333ad25dc75ee6a33bfa3aa6ffb8c07650fc53c29dea5`.

```cmd
benchmarks\task1_extraction\run_all.cmd --source github --limit 10 --concurrency 1 --output-dir benchmarks/task1_extraction/outputs/essayjudge_gemini_3_1_flash_lite
```

Audit requests now respect `--concurrency`, checkpoint each completed verdict,
print progress and retain API failures in `audit_errors.jsonl`. If an audit fails,
the HTML marks it `audit_failed` (not a factual alignment verdict), and the command
returns a nonzero exit code. Resume reruns only unfinished audits.

Use `audit_consistency --allow-partial` to render missing extractions explicitly
when an API outage prevents completion. The partial report still returns a nonzero
exit code. Normal runs remain strict and stop before auditing incomplete input.

## Real EssayJudge benchmark result

Model `gemini-3.1-flash-lite`, first 10/121 unique prompts (not a stratified sample):
10/10 successful extractions and 10/10 completed audits. The initial concurrency-3
run saved six extractions and logged four HTTP 503 high-demand failures after
retries. Resuming with concurrency 1 recovered all four without rerunning successes.
Routing: 3 auto_verified / 7 needs_user_check. Audit: 5 consistent / 4 minor_variance /
1 conflict. The conflict notes describe rounding/approximation differences, so this
verdict itself needs human review; it does not prove a visual extraction error.

Successful-record extraction latency: p50 6,362 ms, p95 23,947 ms. Extraction usage:
12,651 input tokens and 9,653 candidate tokens. These omit earlier failed requests
and are not end-to-end wall time or a complete billing estimate. Confidence and
silver consistency are not independently reviewed extraction accuracy.

Outputs: `outputs/essayjudge_gemini_3_1_flash_lite/` contains extraction checkpoints,
audit checkpoints, retained initial errors, `benchmark_summary.json`, and the
self-contained `review_report.html` (923,859 bytes; 10 embedded JPEGs validated).
Nine offline regression tests and Python compilation passed.

The complete `run_all.cmd --source github --limit 10 --concurrency 1` rerun
finished with exit code 0: 10 cached extractions, 10 cached audits, no pending
Gemini requests. Production code and the existing `hf_test/` folder were untouched.

## Exhaustive/sanity run on the same ten images

Version `3-exhaustive-sanity` completed 10/10 extraction records. The initial
concurrency-2 invocation completed 7/10, the first concurrency-1 resume reached
9/10, and the second resume reached 10/10. Each image invocation used at most five
API attempts. Earlier failed invocations remain in extraction_errors.jsonl; do
not call this a single-invocation 10/10 or claim that retry eliminates 503 outages.

Scalar grid coverage against the prior visual position inventory rose from 97/192
(50.5%) to 192/192 (100%). Weather: two tables, 4x12 + 2x12 = 72 cells; travel:
6x4 = 24 cells; Australia population: 12 cells. This validates structural counts,
not numeric correctness or independently reviewed recall. The weather estimates
still need review; in a visual spot check, Brisbane maximum in March/April appears
around 24/19 degrees, while this extraction gives 26.5/23.5. The process steps no
longer claim pumped or closed-loop mechanisms, but the free-text notes still use
'cyclical', which is not established as a recycling loop by the diagram.

Travel retains the literal 680.5 and is flagged total_row_mismatch (1048.9 versus
448.9). The 2008 pie retains its printed slices and is flagged sum=102.0%. Both
route needs_user_check with confidence <=75. Routing is 1 auto_verified (milk)
and 9 needs_user_check. Travel's overview still contains an inconsistent Europe-
highest claim; the source arithmetic alert and forced review protect the route,
but deterministic checks cannot certify every natural-language overview claim.

Successful-record extraction latency including internal retries: p50 30,415 ms,
p95 161,240 ms, mean 59,063 ms. Mean item total: 59,071 ms. These omit previous
failed invocations, queue wait, preparation and silver audit; they are not a
fresh full-pipeline user-visible latency estimate. Four failed image invocations
(20 failed attempts) plus successful invocations (24 attempts) total 44 extraction
attempts. Missing usage on failures means token totals are known lower bounds.

`coverage_comparison.json` contains the per-image matrix sizes and the comparison
definition. There is no verified_gold.jsonl yet; the evaluator correctly refuses
to issue real accuracy/F1/MAPE in its absence. 18 offline tests pass, including
synthetic exact/tolerance/MAPE/routing metrics, shape/sum routing, resume and errors.

Fresh silver audit completed 10/10 after a concurrency-1 resume (first invocation
4/10; six failed audit invocations retained with attempt-level telemetry). Milk
now receives minor_variance for rounding rather than the earlier false conflict.
The HTML was checked for ten valid embedded JPEGs, all 192 numeric cells, both
arithmetic alerts, stage timings and no missing/failed audit placeholders. The
original v2 output checksums were preserved. No verified gold accuracy is inferred.

Final full entrypoint rerun (without --skip-audit) exited 0: all 10 extraction
and all 10 audit records were cached; no new Gemini requests were needed.
