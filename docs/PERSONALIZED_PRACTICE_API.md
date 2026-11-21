# Personalized practice API

## Classroom pilot contract

All paths below are prefixed with `/api`. Requests use a Clerk bearer token. Backend ownership requires the submission owner and an active class membership; staff review uses separate teacher routes. Client-supplied user IDs do not grant access.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/writing/task2/{submission_id}/exercises` | Practice state and public exercises |
| POST | `/writing/task2/{submission_id}/exercises` | Start generation or reconnect to a pending job |
| GET / PUT | `/writing/task2/{submission_id}/practice-attempt` | Restore/save complete-set answer drafts |
| POST | `/writing/task2/{submission_id}/practice-attempt/submit` | Submit a complete set for evaluation |
| GET | `/exercises/{exercise_id}/feedback` | Last applicable feedback |
| POST | `/exercises/{exercise_id}/answer` | Supported individual-answer API; current UI uses complete sets |
| POST | `/exercises/{exercise_id}/hint` | Request a hint |
| POST | `/writing/task2/{submission_id}/revision` | Evaluate an approved paragraph revision |
| GET | `/writing/task2/{submission_id}/progress` | Persisted learning progress |

Operations requiring AI return HTTP 202 with a job ticket and `poll_url`. Poll `/jobs/{job_id}` until `COMPLETED` or `FAILED`; successful results are in `result`. Queue admission and idempotency are enforced on the server. Public exercises hide reviewed answer keys until the appropriate feedback operation. Rewriting accepts multiple valid responses and does not expose a fixed reference answer.

The frontend restores saved answers and submits all exercise IDs once the set is complete. Schema and ownership validation remain authoritative. API payload details are defined in `app/practice/schemas.py` and routes in `app/routers/pilot.py`; do not infer them from archived demo screenshots.

## Failures and limits

401 means absent/expired authentication; 403 means permission/active-membership or consent failure; 404 means unavailable or unowned resources; 409 indicates conflicting input/state; 422 indicates schema validation; 429 indicates an applicable quota; 503 may indicate full queue or unavailable service. Provider failures of admitted jobs are exposed through safe job error codes. A failed practice operation preserves the successful assessment and does not refund its essay grading credit.

Practice may contain fewer than the requested items, including none when review rejects every candidate. Grading/practice generation and answer evaluation consume provider budget; hints, key-based checks and reads generally do not call Gemini. High-band refinement and retries can require extra calls. Token/cost data are estimates and may be unavailable.

## Local demo

`app.main:app` provides a separate cookie-owned SQLite adapter with shared practice schemas. Some responses are synchronous rather than pilot job tickets. Use [demo instructions](DEMO_GUIDE.md); historical measurements are under [archive](archive/README.md).
