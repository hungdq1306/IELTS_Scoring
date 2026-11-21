> Historical snapshot. This document records an earlier implementation or proposal. For current behavior, see [documentation](../README.md) and [architecture](../ARCHITECTURE.md).

Complete-set practice feedback — 2026-11-20

Students write every response before submitting the practice set. Moving between exercises saves drafts without evaluating them. The browser also retains local drafts between saves. A blank or missing response prevents submission, and the backend independently validates ownership, IDs and completeness.

One Gemini 3.1 Flash-Lite call assesses the complete set and provides per-exercise explanations plus an overall practice summary. MCQ correctness is checked against the reviewed backend key even when the model disagrees. Rewriting accepts multiple valid formulations and never returns a fixed answer to the UI. No new IELTS overall band is assigned to a practice set.

Configuration:

```dotenv
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_PRACTICE_ANSWER_MODEL=gemini-3.1-flash-lite
```

The first setting continues to control essay grading and exercise generation/review. The second controls practice answer evaluation and paragraph-revision feedback. There is no silent fallback to another model. Existing quota accounting and provider retry limits remain active.

New endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/writing/task2/{submission_id}/practice-attempt` | Restore draft answers and the latest applicable result |
| PUT | `/api/writing/task2/{submission_id}/practice-attempt` | Save partial or complete drafts; no model call |
| POST | `/api/writing/task2/{submission_id}/practice-attempt/submit` | Submit every exercise for a single batch evaluation |

PUT takes `answers: [{exercise_id, answer}]`. POST additionally requires `request_id`. Inputs and the public POST/GET response contracts use Pydantic. A result contains `items`, `correct_count`, `total`, `summary`, `evaluation_model` and `human_reviewed: false`.

SQLite stores practice_drafts and practice_attempts in the existing practice database. Completed feedback and per-exercise progress are committed atomically. A failed evaluation publishes no partial progress. Same-key duplicates and identical completed submissions reuse their persisted result. Changed answers under the same request ID are rejected. At most three batch submissions, including failed submissions, are allowed per essay. A pending/interrupted submission is not automatically rebilled.

Compatibility: existing per-exercise answer endpoints and standalone revision endpoints remain for older clients. The current FogWrite practice workspace uses the complete-set endpoint and hides individual Check answer controls. The full-set completeness rule applies to the new batch endpoint; it is not a removal of the older API.

Real demo results:

- Real essay grading: Gemini 3.5 Flash-Lite, HTTP 200.
- Real generation and independent automated review: three approved exercises, zero exclusions (MCQ, guided rephrase, error imitation).
- Real complete-set evaluation: Gemini 3.1 Flash-Lite, three responses assessed in one model request, 3/3 correct for the manually written demonstration responses.
- Evaluation elapsed time: 8,888 ms including local provider pacing; provider request latency: 6,876 ms.
- Evaluation tokens: 1,385 input + 432 output = 1,817 total.
- Four generateContent requests for the complete essay-to-practice flow: one essay grade, two practice generation/review calls, one answer evaluation. Model-list access checks are separate from generation requests.
- Browser checked disabled submit before completion, no per-question requests, draft saves, results after submission, idempotent replay and restoration through History. Subsequent browser replay used the persisted real-model result, not another API call.
- Backend: 39 tests passed. Frontend unit/render tests: 16 passed. Offline browser contracts passed at 1440×900 and 1280×800; those contract fixtures are not real Gemini results.

See `PRACTICE_BATCH_DEMO_RESULTS.json` for sanitized real-call metadata and feedback. The private browser context used for the demo is not exported because it contains a session cookie. This single demonstration is not an exercise-quality benchmark or evidence of learning gains.

Run from the repository root in PowerShell:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH='backend'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

For the prepared workspace runtime, `.cache/runtime-py` can be prepended to PYTHONPATH as in scripts/start-fogwrite.ps1. Dependencies for the offline build were installed into `.cache/ui-deps/node_modules` using verified npm package archives. Build commands:

```powershell
$env:FOGWRITE_NODE_MODULES=(Resolve-Path '.cache/ui-deps/node_modules').Path
node scripts/build-frontend.cjs
node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-ui.test.cjs
```

To demonstrate: open the studio, grade an essay, choose Practise priority skills, generate exercises, write each response, use Next exercise, then Submit all responses. Review the summary and each exercise's feedback. Return through History to restore the answers and results. New user sessions require their own essay submission; the demo session cookie is not shared.
