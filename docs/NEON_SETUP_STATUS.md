# Clerk + Neon MVP setup — 20 November 2026

## Connected services

- Neon MCP is connected to the requested organization `org-delicate-frog-24471273`.
- Project: **FogWriting**, `calm-field-59370545`; production branch: `br-rapid-sea-b3fzvvzs`.
- Region: AWS Singapore (`aws-ap-southeast-1`); database: `neondb`; PostgreSQL 18.
- The supplied Clerk development Publishable Key has been saved locally. Issuer: `https://select-bee-2083.clerk.accounts.dev`.
- Application identity stays with **Clerk**. Neon PostgreSQL stores application data. Neon Managed Auth was already provisioned on this branch, but the app does not use it for login. No identities were migrated or linked by email.
- Local server settings now use the pooled Neon database URL. Migrations use the direct URL. Existing Gemini settings were preserved; database passwords are not committed or exposed to the frontend.
- The browser obtains Clerk configuration from `/api/auth/config`; the backend verifies Clerk JWTs with its public JWKS. A Clerk secret key is not needed.

## Applied to the real database

The public schema was inspected and empty before applying the migration. The SQL was generated from the existing Alembic revision, with the same default records as `app.seed.seed_defaults`, then applied in one transaction through Neon MCP.

The first transaction failed with a SQL quoting/transport encoding error and rolled back completely. Unicode-safe transfer fixed it; the second transaction committed all 39 statements successfully.

Live verification query result:

```text
migration      tables  anchors  exercise_templates  prompts  users
0001_pilot     14      8        3                   3        0
```

The 14 tables include `alembic_version` and 13 application tables. There are no student accounts or submissions yet. The default exercises cover contextual multiple choice, guided rewriting, and error transfer.

Alembic now supports standard offline SQL generation (`upgrade head --sql`). Future schema changes should use new Alembic revisions.

## Verification results and limits

```text
python -m pytest -q backend/tests/test_neon_configuration.py backend/tests/test_clerk_setup.py --tb=short
19 passed in 0.44s

node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-ui.test.cjs
tests 16; pass 16; fail 0

node scripts/build-frontend.cjs
frontend/dist/app.js 259.2kb
frontend/dist/app.css 29.9kb
FogWrite Screen Design 01 built (5b53ddff8f39).
```

The direct Node build and frontend tests use cached dependencies (`FOGWRITE_NODE_MODULES` and `NODE_PATH` point to `.cache/pilot-ui-deps/node_modules`, with `ESBUILD_WORKER_THREADS=0`). The initial frontend test attempt could not resolve dependencies until these existing cache paths were supplied. These checks do not establish that `npm run build` passes.

Checks that could not complete in this execution environment:

- `npm run build`: `npm` is not installed/discoverable. The earlier global Neon CLI installation, `npx` fallback, init and deploy were also unavailable. MCP performed the actual database setup instead; no CLI deployment is claimed.
- Clerk JWKS HTTP request: DNS error `getaddrinfo failed`.
- FastAPI startup: Python's asyncio loop stalled in Windows `socket.socketpair()/accept()`, before application startup. A 12-second diagnostic timeout stopped it. There is no running server from this attempt.
- Consequently, real browser sign-in, a protected FastAPI request against Neon, and a new Gemini scoring run have not been verified. Successful MCP database write/read and mocked tests do not prove those application flows.

## Start on your Windows host

The database and Clerk configuration are already saved. Run **`RUN_FOGWRITE_CLERK.cmd`** from the project root, then open **http://localhost:8000**. Keep the terminal open. This uses the existing prebuilt frontend and needs no npm to start.

Do not run the older `RUN_FOGWRITE.cmd` for this test: that entry point starts the research/demo application.

If Python dependencies are missing:

```powershell
python -m pip install -r backend/requirements-dev.txt
```

The launcher adds the backend to `PYTHONPATH`. For manual commands:

```powershell
$env:PYTHONPATH = 'backend'
python -m app.setup_clerk --check
python -m uvicorn app.pilot:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

After Node.js 22+ with npm is installed, the requested standard build command is:

```powershell
npm install
npm run build
```

Use `localhost:8000` consistently because it is the configured authorized frontend origin.

## First teacher account and end-to-end acceptance

1. Open the app and sign in with Clerk. Check enabled login providers in the Clerk Dashboard; the public key cannot change provider settings.
2. Copy the signed-in account's `user_...` ID from Clerk Dashboard > Users. In another terminal, grant teacher access:

```powershell
$env:PYTHONPATH = 'backend'
python -m app.manage grant-role --clerk-user-id user_REPLACE_WITH_REAL_ID --role teacher
```

3. Refresh the account panel, create a class, and keep its generated invite code. Complete the existing consent flow.
4. Sign in as a student in a separate browser profile, join that class, and submit an essay. Verify queued scoring, criterion feedback, sentence annotations and generated practice.
5. Submit the full practice set and check its feedback. Refresh to verify saved state.
6. Sign out; protected operations must reject requests. A student must not be able to read another student's submissions or teacher routes.
7. Verify `/health`, `/ready`, and `/api/auth/config`. Readiness should report the real database and worker state.

Do not fabricate a Clerk user ID or grant staff access based on an unverified email address.

## Public deployment

This configuration uses a **Clerk development key** and local origin. The production settings deliberately require a live Clerk instance, HTTPS frontend origin, and confirmed Gemini configuration.

Use the Render Docker deployment steps in [backend/README_DEPLOY.md](../backend/README_DEPLOY.md). Render hosts FastAPI and the built frontend together. The existing Neon project is ready; do not create another database project or overwrite the current credentials. Configure production Clerk DNS/provider settings and copy the required environment variables through the host's secret settings.

`neon deploy` provisions Neon services; it does not host this Python FastAPI application. Neon Managed Auth is not an additional app login flow in this setup.
