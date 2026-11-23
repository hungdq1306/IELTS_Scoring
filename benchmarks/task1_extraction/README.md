# Task 1 visual extraction benchmark

Standalone experiment; no imports or changes to production `app.pilot:app`.
All commands run from the repository root. Requires Python 3.11+, Pillow,
Pydantic v2, google-genai, python-dotenv and datasets (available in `.venv`).
The existing repository requirements supply all except Pillow explicitly;
install missing dependencies with `python -m pip install -r benchmarks/task1_extraction/requirements.txt`, without changing production dependencies.

```cmd
benchmarks\task1_extraction\run_all.cmd --limit 5
benchmarks\task1_extraction\run_all.cmd --limit 0 --model gemini-2.5-flash --concurrency 3
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

Default source is `EssayJudge/EssayJudge`, as requested. This identifier could
not be accessed on 2026-11-23 (HTTP 401 / DatasetNotFoundError). No alternate
corpus is silently substituted. Supply a valid `--dataset-name` or `--local-file`
JSON/JSONL/Parquet containing images, questions, essays and human scores.
Column names are matched case-insensitively with separators normalized.
Images can be PIL images, HF bytes/path objects, or paths relative to the local file.
Score selection prefers overall, then task achievement/response, then mean of
available score/band columns. Only supply human scores in these fields; model
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
- Default five-image end-to-end command stops at inaccessible EssayJudge source.
- A separate five-image synthetic bar-chart fixture exercises local preparation.
  It is not EssayJudge and cannot measure quality on real IELTS visuals.
- `gemini-2.5-flash` returned HTTP 404 (unavailable to new users). The default is
  retained to follow the plan; use `--model` to select an accessible model.
- `gemini-3.8-flash`: three recorded 504 errors before stopping the slow run.
- `gemini-3-flash-preview`: 2/5 synthetic images extracted; 3/5 returned 504.
  Both successful extractions were audited as consistent, and the portable report
  was generated at `outputs/synthetic_smoke/review_report.html` (65,017 bytes,
  two embedded JPEGs validated). This is a successful-subset report, not a 5/5 run.
  Resuming this subset selected 2 cached records with 0 pending API requests.
  Successful extraction p50 was 31,070 ms and p95 was 38,720 ms; these two samples
  do not establish real-data latency or extraction accuracy.

The full requested EssayJudge benchmark remains unverified until an accessible
real dataset is supplied. The synthetic fixture, checkpoints and failed requests
are retained locally under ignored `data/` and `outputs/` folders.
