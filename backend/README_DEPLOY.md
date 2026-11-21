# FogWrite classroom pilot deployment

This guide applies to `app.pilot:app` (Clerk + PostgreSQL). `RUN_FOGWRITE.cmd` starts the separate cookie-session research/demo server `app.main:app`. Do not deploy that demo as the classroom API.

## Configuration

Copy the relevant entries from `backend/.env.example` into the root environment without replacing existing keys. Never commit `.env`, tokens or database passwords.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `production` on the hosted pilot; `development` for local Clerk |
| `DATABASE_URL` | PostgreSQL pooled runtime connection |
| `MIGRATION_DATABASE_URL` | Direct PostgreSQL connection for Alembic; `DATABASE_URL_UNPOOLED` is a supported fallback |
| `FRONTEND_ORIGIN` | Exact frontend origin, no path; used for JWT authorized-party checks and CORS |
| `CLERK_ISSUER` | HTTPS issuer for the selected Clerk instance |
| `CLERK_PUBLISHABLE_KEY` | Public key; production validation requires `pk_live_...` |
| `CLERK_SECRET_KEY` | Server-only optional profile fallback/backfill; recommended when JWTs omit name/email |
| `GEMINI_API_KEY` | Server-only provider credential |
| `GEMINI_MODEL` | Essay grading and practice generation model |
| `GEMINI_PRACTICE_ANSWER_MODEL` | Smaller practice answer/revision evaluator |
| `GEMINI_DATA_POLICY` | Explicit confirmed policy; production rejects `unconfirmed` |
| `GEMINI_MAX_RPM`, `GEMINI_MAX_TPM`, `GEMINI_MAX_RPD`, `GEMINI_MAX_CONCURRENT` | Budget limits appropriate to the provider account |
| `RETENTION_DAYS`, `WORKER_COUNT`, `WORKER_ENABLED` | Retention and in-process queue workers |

See `app/pilot_config.py` for defaults and validation. Student daily credits reset at 00:00 Asia/Ho_Chi_Minh; they use the maximum active class quota plus applicable bonus. Staff defaults come from system settings. Permanent essay failure releases student credits; global daily admission accounting includes failed admissions and operator retries. Practice has separate request/attempt limits.

## Local authenticated development

Run `SETUP_CLERK.cmd` with your development publishable key, then `RUN_FOGWRITE_CLERK.cmd`. The helper preserves existing provider configuration. Create/join classes with real development identities; use the trusted role command below to bootstrap administration. Local demo startup remains `RUN_FOGWRITE.cmd`.

## Schema and initial data

Use the intended target environment. Run from the repository root:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
.\.venv\Scripts\python.exe -m app.manage seed
```

Current head is `0003_operator_identity`. The migrations add RBAC/settings and profile metadata while preserving existing application rows. The nullable join-code field uses the unique index `ix_classes_join_code` in both migration and model. Existing memberships with unknown historical join dates may retain zero.

Before deploying changed schema to real data, verify backup/restore and migration compatibility. Do not run pytest reset fixtures against the pilot database. Use `fogwrite_test` for reset tests and a separate `fogwrite_migration_test` for actual migration verification. Do not downgrade the live database as an automatic rollback step.

Bootstrap an administrator only with a verified Clerk user ID:

```powershell
.\.venv\Scripts\python.exe -m app.manage grant-role --clerk-user-id user_REPLACE_WITH_VERIFIED_ID --role admin
```

New accounts default to students. Subsequent role/bonus/status changes use authenticated admin APIs with audit records. Assigned TAs have read-only class review. The current admin and last active admin are protected by the web governance routes.

## Build and Render release

`backend/Dockerfile` builds the frontend with Node/Vite and runs Python with `uvicorn app.pilot:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`. `render.yaml` is the service blueprint; it does not create Neon/Clerk identities, populate secrets or apply migrations.

1. Run [verification](../docs/VERIFICATION.md), including the isolated PostgreSQL suite and migration check.
2. Build the Linux image: `docker build -f backend/Dockerfile -t fogwrite-pilot .`.
3. Inspect the release diff, include migrations/new source and commit the frontend bundle for local preview. Docker independently rebuilds the frontend.
4. Ensure the target database is migrated before the matching code receives traffic. Confirm runtime secrets on Render; do not print them in logs.
5. Push the intended commit to the connected GitHub branch and observe the Render build/deploy. A successful git push is not proof of deployment.
6. Verify the deployed commit, `/health`, `/ready`, public assets and live class flows. `/ready` checks database reachability, anchors and worker tasks, not all migration columns or provider/Clerk integration.

A sleeping/free host may pause in-process workers; no always-on guarantee is made. Separate frontend hosting requires an explicit `/api` proxy/origin/CSP design and is not configured by this repository.

## Acceptance and monitoring

Use authorized staging/test identities to check student, TA, teacher and admin permissions; class invitations/rotation/removal; duplicate submission/idempotency; quota and failure refund; History/refresh; account switching while a request is pending; practice generation and complete-set answers. Confirm the deployed pilot does not expose `/api/benchmarks` or `/api/datasets`.

Admin provides account filters, changes with reason/audit, class quota settings, usage/pricing, queue/failed jobs, safe retry and activity filters. Empty model prices mean unavailable cost, not zero. Usage records do not guarantee reconciliation with provider invoices. Job lease fencing prevents stale workers publishing results, but a crash can still cause a repeated provider call.

Privacy consent is explicit; do not submit sensitive data. Retention cleanup runs hourly while workers are enabled and the instance is active, not at an exact deletion deadline. Operator commands support dry runs:

```powershell
python -m app.manage purge-expired
python -m app.manage purge-expired --apply
python -m app.manage delete-writing --clerk-user-id user_REPLACE_ME
python -m app.manage delete-writing --clerk-user-id user_REPLACE_ME --apply
python -m app.manage set-active --clerk-user-id user_REPLACE_ME --active false
```

Deleting writing preserves the auth/membership/audit account context; deleting Clerk identities is a separate operator action. Wait for active jobs before deleting their writing. Roll back an application image only after checking schema compatibility.

## Verification boundaries

Offline tests mock AI; browser fixtures mock Clerk/API. The basic Gemini live test verifies provider access/scoring, not all practice flows or accuracy. Evaluate experimental v2 independently on held-out teacher-scored essays. Historical v1 metrics and older setup/deployment records are preserved under [archive](../docs/archive/README.md); use [current verification](../docs/VERIFICATION.md) for evidence and limits.
