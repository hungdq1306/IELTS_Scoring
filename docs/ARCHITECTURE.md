# System architecture

## Classroom pilot

Render builds `backend/Dockerfile`: Vite compiles `frontend/src/fogwrite.jsx`, then Python serves the bundle and `app.pilot:app` from one origin. `render.yaml` describes the service. The production image includes the frozen seed anchors, not the research datasets.

The frontend obtains public Clerk configuration from `/api/auth/config` and sends bearer tokens. `auth.py` verifies JWTs; `identity.py` caches verified display profiles. Backend role, class ownership and membership checks authorize every resource. `auth-context.jsx` coordinates session changes; drafts, History requests and practice workspaces are scoped to the account. In-flight assessment/restore requests are aborted and fenced when accounts change.

`routers/pilot.py` admits submissions under serialized quota/queue checks, persists their configuration snapshot and creates jobs. PostgreSQL row locks and leased claims coordinate workers. `worker.py` runs grading/practice outside database sessions, renews leases and fences stale results. Final failures record their completion time. Operator retry is audited, checks queue/quota capacity and refuses an existing assessment. Provider calls can repeat after crashes; billing is not exactly-once.

`services/scorer.py` applies v1 or experimental evidence-first v2, grounds annotations, applies teacher/global offsets and computes rounded bands. `services/drill_gen.py` validates source evidence and independently reviews exercises, including high-band refinement. Complete-set answers use the smaller evaluator; MCQ keys remain authoritative. No practice score is an IELTS band.

PostgreSQL stores application records and usage. Student limits use active class quotas; credits reset at 00:00 Asia/Ho_Chi_Minh. Failed essay jobs refund student credits; global admission limits retain failed admissions. Admin routes manage accounts/settings/jobs/audit and report usage; missing prices do not mean zero cost.

## Local demo and research

`app.main:app` is a separate cookie-session demo with SQLite-backed research/practice services and benchmark APIs. It is still used by launchers and tests; it is not deployed by Render. `backend/benchmark/`, `src/data/` and `src/eval/` provide dataset preparation, evaluation and report CLIs. Keep frozen artifacts for reproducibility; v1 metrics must remain labeled as v1.

## Operations

Alembic revisions in `backend/alembic/versions/` define schema history. Test fixtures using `create_all` do not validate migrations: separately run upgrade/current/check against an isolated migration database. `/health` reports process health; `/ready` checks anchors, database reachability and worker tasks, not every migration column or external service.

See [deployment](../backend/README_DEPLOY.md), [verification](VERIFICATION.md) and [practice API](PERSONALIZED_PRACTICE_API.md).
