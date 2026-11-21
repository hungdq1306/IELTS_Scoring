> Historical snapshot. This document records an earlier implementation or proposal. For current behavior, see [documentation](../README.md) and [architecture](../ARCHITECTURE.md).

Contextual multiple choice and open-ended rewriting

Update 2026-11-20: the current UI defers all answer checking until the entire practice set is submitted. It uses a separate Gemini 3.1 Flash-Lite evaluator. The frontend dependency/build blocker described in the original validation notes below has been resolved: 16 frontend tests and a real browser-to-backend practice demo have now passed. See PRACTICE_BATCH_DEMO.md and PRACTICE_BATCH_DEMO_RESULTS.json for current results; the older notes describe the earlier iteration.

Multiple choice

- Vocabulary practice asks for the best word, contextual synonym, collocation or register choice in a complete sentence. Near-synonyms are not interchangeable in every context.
- Grammar practice targets the verified source error using appropriate word forms or constructions. Synonym selection is classified as vocabulary rather than a grammar improvement.
- The generator must explain the best choice and the contextual problems with distractors. Independent automated review rejects ambiguous items. This is not a guarantee of human-verified answer quality.
- Accepted MCQs retain a backend answer key and are checked deterministically without another Gemini request.

Rephrase / sentence_rewriting

- Free rewriting supplies a new sentence and asks the learner to preserve its intended meaning while practising the source skill.
- Guided rewriting also supplies `structure_prompt`, for example `Although + clause, + main clause.`. This is an incomplete generic structure, not a filled-in answer.
- A structure is advisory unless the exercise instruction explicitly requires the transformation.
- Learners write their own responses. The evaluator accepts alternative vocabulary and structures that meet the instruction, preserve meaning and avoid serious new errors. No exact-key comparison is used for rewriting, even for responses identical to the internal sample.
- A backend reference remains available for generation/review as one possible solution, not as the only correct answer. Rewriting answer responses use an empty `correct_answer` and empty `accepted_alternatives`; the UI does not render a Reference answer panel for rewriting. Explanations and specific suggestions are shown after submission.
- MCQs and other existing exercise types retain their current answer contracts.

API and persistence

`structure_prompt` is an optional string (maximum 1,000 characters) on generated and public exercise records. Empty or absent means no scaffold. Existing stored batches work without migration, and old rewriting feedback keys are redacted when returned. New generation metadata uses `practice-v1.2-contextual-rewriting`. Existing ready batches remain idempotent and are not silently regenerated or rebilled.

The generator now requests a recognition → rewriting → transfer sequence for a verified language weakness. It must not invent a language error when only discourse weaknesses are present. Rewriting uses the existing Gemini answer evaluator, response idempotency and attempt limits; generation and grading prompts remain separate.

Validation for this change

- `PYTHONPATH=backend python -m pytest backend/tests/test_practice.py -q`: 15 passed. These are offline tests with provider fixtures, not real Gemini results.
- Backend tests cover multiple accepted rewrites, evaluation routing, hidden keys, scaffold leakage/injection checks and deterministic contextual MCQ checking, alongside existing persistence/ownership/retry tests.
- Added frontend rendering tests for guided/free rewriting and contextual MCQs. They could not be executed in the current checkout because frontend dependencies including `esbuild` are unavailable. The frontend build fails with `Cannot find module 'esbuild'`; no successful build is claimed.
- No real Gemini requests were made for this change. Pedagogical effectiveness and real-model exercise quality have not been established by these offline checks.
