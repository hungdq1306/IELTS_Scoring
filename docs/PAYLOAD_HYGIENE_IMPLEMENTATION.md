# Payload hygiene and independent TR/CC implementation

Branch: `hung/task2-claude-haiku55-eval`; review baseline: `f607678`.

## Implemented behavior

- One target question and one target essay in a JSON payload. Verified paragraphs are labeled `[pN]` in both targets and anchors.
- Paragraph spans refer to unchanged source substrings. Labels never become evidence or saved essay text.
- Unknown paragraph boundaries stay unverified; CC instructions prohibit treating missing source formatting as a student error.
- Current overall policy `half_band_threshold_0375_v1`: .375/.875 round up; .25/.75 round down, using Decimal. This supersedes the original strict-floor policy. Criterion midpoint aggregation and calibration rounding remain separate.
- Teacher-reported overall labels are retained independently from computed overall.
- Anchors are selected by independent score provenance and loaded feedback; no essay-ID cue tables remain.
- Anchor serialization is allowlisted: four criterion scores and verified criterion feedback, without overall or legacy cues.
- TR and CC have separate evidence/ceiling rules. Word count and repetition statistics alone do not cap a score.
- Default DB anchor sync only updates/retires system-owned `default-` rows. Teacher-owned rows, including colliding IDs, are preserved.
- Old empirical confidence percentages are unavailable (`null`) until validated for this prompt/policy.
- Live evaluation resume rejects caches from a different prompt/model/data/overall policy before provider execution.

## Frozen dataset

The membership manifest retains both the original Windows checkout hashes and the original Git blob hashes. Tests respect Git’s existing LF/CRLF checkout policy; the implementation-run invariants separately enforce the exact original Windows bytes. No dataset line endings were changed.

No splitter was run against the frozen artifacts. Dev and holdout bytes are preserved; seed text, prompt, order, membership and cluster IDs are preserved. The splitter refuses an output directory containing the frozen membership manifest.

| Split | Records | SHA-256 before hygiene (dev/holdout remain identical) |
|---|---:|---|
| seed | 15 | `7b9da6197774dffbc6a425a404ebd6a54c5822b8d73947da40a2a456e6145e01` |
| dev | 173 | `e0d1e13dfde444e61a36dea76b0c19d383bc148ca769b895a1f5a86711d83c5c` |
| holdout | 63 | `2eb6efe23882d4ae0b66f2993a49e159c829ca81db82d11e433a12134cf61ce0` |

## Seed provenance and overall labels

| ID | TR | CC | LR | GRA | Reported | Computed current policy | Score source |
|---|---:|---:|---:|---:|---:|---:|---|
| 60d15778a7220c00129d0fef | 5.5 | 5.5 | 5.0 | 4.5 | 5.0 | 5.0 | dual_rater |
| 6756f7ea91514b0011fd65e2 | 6.0 | 5.5 | 4.5 | 4.5 | 5.0 | 5.0 | dual_rater |
| lecturer_02 | 6.0 | 6.0 | 6.0 | 7.0 | 6.5 | 6.0 | examiner_verified |
| lecturer_03 | 7.0 | 7.0 | 6.0 | 6.0 | 6.5 | 6.5 | examiner_verified |
| lecturer_04 | 5.0 | 6.0 | 6.0 | 6.0 | 6.0 | 5.5 | examiner_verified |
| lecturer_05 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | examiner_verified |
| lecturer_06 | 8.0 | 8.0 | 8.0 | 7.0 | 7.5 | 7.5 | examiner_verified |
| lecturer_07 | 8.0 | 8.0 | 8.0 | 8.0 | 8.0 | 8.0 | examiner_verified |
| lecturer_08 | 8.0 | 8.0 | 8.0 | 8.0 | 8.0 | 8.0 | examiner_verified |
| lecturer_09 | 8.0 | 8.5 | 8.5 | 9.0 | 8.5 | 8.5 | ai_augmented |
| lecturer_10 | 8.5 | 9.0 | 8.5 | 9.0 | 9.0 | 8.5 | ai_augmented |
| lecturer_11 | 8.5 | 9.0 | 8.5 | 9.0 | 9.0 | 8.5 | ai_augmented |
| lecturer_12 | 8.5 | 9.0 | 8.5 | 9.0 | 9.0 | 8.5 | ai_augmented |
| lecturer_13 | 9.0 | 9.0 | 8.5 | 9.0 | 9.0 | 9.0 | ai_augmented |
| lecturer_14 | 9.0 | 9.0 | 8.5 | 9.0 | 9.0 | 9.0 | ai_augmented |

## Paragraph source audit

The twelve exceptions contain nine single-newline records and three records with no newline. Raw upstream boundaries are unavailable: supplemental raw paths are absent; Writing9 CSV records are the available ingestion source. Candidate annotations are not accepted as verified paragraphs. No source text was rewritten.

| Split | ID | Status | Verified |
|---|---|---|---|
| seed | lecturer_11 | hard_wrapped | false |
| seed | lecturer_12 | hard_wrapped | false |
| seed | lecturer_13 | hard_wrapped | false |
| seed | lecturer_14 | hard_wrapped | false |
| dev | 5d5672b78482ba0017ec7d0a | single_newline_candidates | false |
| dev | 5e515634b5257a00117ddf60 | single_newline_candidates | false |
| dev | 5e6c2b42fcf42e0018cc74a0 | single_newline_candidates | false |
| dev | 5ead2be2f3aa390018407dfb | single_newline_candidates | false |
| dev | 5f3f3321b66d150018c2f1b6 | single_newline_candidates | false |
| dev | 63d635bf507b340018bede74 | no_boundaries | false |
| dev | 6555ff8c10f6a900136b6c7a | no_boundaries | false |
| holdout | 63c6caf933b0da001866926a | no_boundaries | false |

## Offline verification

Verification of the preceding strict-floor version (retained as historical evidence):

| Check | Result |
|---|---|
| Full Python offline suite | 153 passed, 1 skipped, 1 deselected; 0 failures (434.95 s) |
| Dataset portability recheck | 3 passed |
| Frontend diagnostics/highlight tests | 11 passed |
| Offline frontend build | Passed; generated assets restored to tracked content |
| Half-band arithmetic | All 130,321 valid criterion combinations passed |
| Frozen dataset and source audit | Passed; zero dataset-ID literals in Python source |
| Paid API calls | 0 |

PostgreSQL migration integration was skipped because no external test database was enabled; the real Gemini test was deselected by `not live`. An existing Starlette/httpx deprecation warning was emitted.

Machine-readable evidence: `artifacts/hygiene_verification/offline_tests.xml`, `results.json`, and `invariants.json`.

The first broad run exposed two obsolete expectations (eight anchors and root-level word_count/length_note). Those tests were updated to the approved metadata-driven contract, then the full suite above passed.

Commands:

```powershell
$py = 'D:\University\DA_DS\Projects\IELTS_Scoring\.venv\Scripts\python.exe'
& $py -B -m pytest --offline --windows-udp-wakeup -q -m "not live" --junitxml=artifacts/hygiene_verification/offline_tests.xml tests backend/tests
node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-diagnostics.test.mjs
$env:FOGWRITE_NODE_MODULES='D:\University\DA_DS\Projects\IELTS_Scoring\node_modules'
node scripts/build-frontend.cjs
```

`--windows-udp-wakeup` is an explicit test-only adapter for this Windows sandbox: it replaces the blocked TCP self-pipe with local UDP and bounds IOCP polling to service worker-thread callbacks. It is not loaded by the application. `--offline` blocks external connections and disables external test databases. SQLite tests do not establish production/Postgres load behavior.

Fake-provider score preservation tests validate the contract; they do not establish Gemini or Claude grading accuracy. No paid grading or new holdout benchmark is authorized by this implementation run. Historical benchmark artifacts remain historical and are not relabeled as results for the new prompt.

## Rounding correction requested after review

Current rule: `7.875 -> 8.0`, `7.375 -> 7.5`, while `7.75 -> 7.5` and `7.25 -> 7.0` remain unchanged. Policy is `half_band_threshold_0375_v1`; strict-floor caches are incompatible. Both overall calculation entry points use the shared Decimal helper. Criterion scores and reported labels remain unchanged; dev/holdout files remain byte-identical. Updated verification is recorded separately in `artifacts/hygiene_verification/rounding_tests.xml` and `rounding_results.json`.

Updated rounding verification: **66 passed**, including all **130,321** criterion combinations, threshold boundaries, backend/evaluation parity, and unchanged dev/holdout bytes. Zero paid API calls. Only computed seed overall values for the two upper-eighth supplemental records change (8.5 -> 9.0); reported labels and all criterion scores are preserved.
