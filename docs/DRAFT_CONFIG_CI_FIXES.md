# Draft, execution configuration and CI fixes — 2026-11-24

## Plan review and decisions

- Retain the existing PostgreSQL 17 service rather than introduce another PostgreSQL 16 service.
- Viewer restoration never writes composer state. Explicit Edit & Resubmit is the only historical-writing-to-composer action.
- Clear the composer on successful grading/cache response only when prompt, essay and draft update timestamp still match the submitted snapshot. Failures retain the draft. Account generation guards remain in place.
- Persist model_name alongside existing score_thinking_budget, prompt_version and feedback_language in config_snapshot JSON. No redundant execution columns or invented historical configuration.
- Forward model/budget per call, without mutating shared provider settings; usage records use the actual requested model. Increment cache_revision to 2 so older potentially mismatched cached assessments are not reused for new requests.
- Add nullable jobs.first_started_at in migration 0006. Historical unknown queue timing remains null. Retries preserve the first claim; explicit operator restart resets it.
- Queue wait means initial submission-to-first-claim; successful processing means the successful scorer invocation (including its internal provider retries); total end-to-end includes queue, prior worker failures and retry backoff. Components are not an additive partition when retries exist.
- Migration test uses a random disposable PostgreSQL schema, upgrades 0003 to head with legacy rows, checks backfill, triggers, indexes and Alembic metadata parity. It does not reset application data.
- History pagination and Task 1 production integration remain deferred.

## Observed GitHub CI failures

Run 45340069799 on commit 851e570:
- Backend failed collection: ModuleNotFoundError: tqdm through test_mvp -> app.main -> benchmark.run. Dev requirements now include tqdm and datasets (also used by dataset tests).
- Frontend failed only at tour: Cannot find module playwright. Tour resolved dependencies from a Windows-local cache; it now uses frontend/node_modules like other browser tests, with an environment override for offline local use.
- Image and Task 1 jobs passed in that existing run.
- Updated the browser assertion for the renamed end-to-end dashboard label.

## Validation

The updated local validation results are recorded in the task response. Real AI calls are excluded. The PostgreSQL test uses the local test cluster; Docker image rebuilding requires a running Docker daemon. GitHub green status must be observed on a run containing these changes before claiming remote CI passed.
