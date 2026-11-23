# Task 1 visual extraction benchmark

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
