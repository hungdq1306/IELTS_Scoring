# Personalized practice evaluation

This pipeline is independent of grading MAE/QWK and changes no grading benchmark configuration. The frozen initial sample uses seven Lexibot and thirteen Writing9 essays with cached real FS1 grading feedback. Neither dataset supplies assumed human-verified error annotations. Selection uses a fixed seed and excludes locked grading data. Model feedback is weak context, not gold.

The real run uses practice-v1.1, up to five candidates per essay, exact source checks and a second Gemini semantic review. Requested scale is 20 essays, approximately 60–100 candidates; publish only what passes. Results are in results/practice_benchmark/summary.json and the two lecturer CSVs. Earlier smoke output used practice-v1 and is reported separately, not mixed into this benchmark.

## Metrics

| Metric | Numerator / denominator |
|---|---|
| Human error precision | Lecturer-confirmed real diagnoses / diagnoses reviewed for reality |
| Human exercise validity | Lecturer-valid exercises / exercises reviewed for validity |
| Human source alignment | Lecturer-aligned exercises / alignment-reviewed exercises |
| Human answer-key accuracy | Lecturer-approved keys / key-reviewed exercises |
| Human explanation accuracy | Lecturer-approved explanations / explanation-reviewed exercises |
| Automated generation success | Published exercises / all candidate exercises across generation attempts |
| Automated rejection | Rejected candidates / all candidates across generation attempts |

Blank human labels are excluded, not scored false. With no lecturer reviews, rates are null and reviewed counts are zero. Automated acceptance must never be labeled human validity. CSVs also collect importance, ambiguity, difficulty and usefulness.

Operational output includes logical calls, provider attempts/failures, logical failure rate, mean and P95 call latency, token usage and calls per essay. Call latency is not whole-session learner time; pacing can affect time. Tokens are provider-reported. Generation success is an automated gate rate, not educational effectiveness. Failed attempts and rejected exercises are retained for audit.

Offline tests use explicit mocked providers for contracts and failure paths. They are not Gemini results. Real provider calls are stored separately in practice_calls, including raw output, model/version, usage, latency, operation and attempts. A standalone real smoke submission used cached real grading so it did not add a grading call.

## Future educational evaluation

The schema can retain observational group and assessment-phase data. No participants are assigned, no intervention is conducted, and no learning effect is computed. A separately approved protocol could compare feedback-only with feedback-plus-practice, recording pretest writing, completion, revision success, unseen-sentence transfer and delayed assessment approximately one week later. Use blinded human ratings, consent, baseline comparability and appropriate uncertainty analysis. Offline exercise correctness cannot establish transfer or retention.

## Known limitations

Independent model review is correlated with generation and can miss linguistic or task-response errors. Exact quotes establish provenance only. MCQ single-best-answer judgments and free-text meaning preservation still need lecturer assessment. Browser cookie ownership is not a full account system. Local SQLite/file locking needs redesign for multi-host deployment. Difficulty adapts with a small transparent heuristic, not calibrated knowledge tracing. No lecturer gold or learning-gain claims are supplied.

## Recorded real benchmark, 18 November 2026

- 20/20 essay batches completed: 7 Lexibot and 13 Writing9.
- 63 candidates over all attempts; 60 in the latest per-essay sets exported for lecturer review; 50 published. Overall automated acceptance 79.37%, rejection 20.63%. The three superseded candidates belong to a batch whose review hit local pacing before its bounded retry. Raw drafts remain stored.
- 38 logical operations, 37 provider attempts, zero upstream failed attempts. One logical review operation was blocked before transmission by local pacing: logical failure rate 2.63%.
- 1.9 logical calls per sampled essay; mean call latency 19.74 s, P95 27.61 s, including local waits; 113,224 provider-reported tokens. No new grading calls were needed for this benchmark.
- Published types: 14 MCQs, 20 sentence corrections, 14 error-imitation passages, 2 paragraph revisions. Error identification appeared in the separate real smoke; sentence rewriting is implemented and covered offline but was not sampled in these 50 published items.
- All human-review denominators remain zero and human rates null. These counts do not establish error precision, human exercise validity, or learning gains.
- Final offline verification: 49 passed, 1 live test deselected. Mock-based tests are separate from these real provider outputs.
- Separate real free-text/revision smoke: Gemini evaluated one alternative answer as correct and one source-paragraph revision as partially correct; both persisted.

## Files added or changed

New practice package: schemas.py, diagnosis.py, prompts.py, service.py, store.py, routes.py and __init__.py under backend/app/practice. Added backend/benchmark/practice.py, backend/tests/test_practice.py, frontend/src/practice.jsx and the five PERSONALIZED_PRACTICE documents. Integration edits: backend/app/main.py, backend/app/api_models.py, backend/app/providers/gemini.py, frontend/src/main.jsx, frontend/src/styles.css and built frontend/dist assets. Runtime artifacts: results/_practice.sqlite3, practice_smoke.json, practice_live_answers.json and practice_benchmark/ manifest, review CSVs and summary. Existing few-shot configurations and grading benchmark scores are preserved.

## Final browser smoke and total practice usage

The actual React application was exercised at http://127.0.0.1:8002/: real A1 grading, opt-in generation of three exercises, deterministic MCQ submission, hint use, deterministic sentence correction, real Gemini paragraph revision, reload, saved-assessment restoration and persisted before/after display. The sample yielded two completed exercises out of three, one hint and an automatically approved revised paragraph. This is functional test data, not learner effectiveness. One browser grading request was blocked by local pacing while the benchmark was active; retry succeeded after the benchmark finished. Screenshot: results/practice_demo.jpg.

Across all new practice runs (benchmark, standalone smoke and browser smoke), the durable call log contains 45 logical operations: 23 generation, 19 review, 1 alternative-answer evaluation and 2 revisions; 45 provider attempts and 125,345 reported tokens. This total excludes the separate successful browser A1 grading request and historical grading benchmarks. Exact MCQ/correction responses and hints added no Gemini calls.
