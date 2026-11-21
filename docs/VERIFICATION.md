# Verification

## Recorded evidence, 21 November 2026

- User's external PowerShell run: backend offline suite with `TEST_DATABASE_URL` set to isolated PostgreSQL `fogwrite_test`: 84 passed, 1 live test deselected. Some tests intentionally create independent SQLite adapters.
- User's migration run on separate PostgreSQL `fogwrite_migration_test`: upgrade reached `0003_operator_identity`; after matching the join-code model unique index to migration 0002, `alembic check` reported no new operations. The backend suite then passed again.
- User's explicit Gemini live smoke test: 1 passed. This covers basic scoring/provider access, not the whole pilot/practice flow or scoring accuracy.
- Frontend build, 18 model/component checks, 20 role/viewport browser cases, direct account-switch draft/timer and pending-restore/History regressions, and offline six-screen smoke previously passed. These use mocked Clerk/API responses.

## Cleanup verification, 21 November 2026

After removing the unused shared feedback UI/helpers and archiving historical documents: production bundle `e47bcda611cc` built; 46 synchronous backend cases, 18 model/component checks, 20 role/viewport cases, account-switch draft/timer and pending-restore/History regressions, and six-screen offline smoke passed. Python syntax and internal Markdown links passed. The cleanup did not change backend behavior. The full PostgreSQL suite and basic Gemini test above were reported by the user before cleanup; they were not re-run by the agent in the restricted runtime.

Deployment status must be confirmed from the remote service; this document is not a claim that the checkout has been published.

## Commands

Run from the repository root. Never point backend reset fixtures at real pilot data.

```powershell
docker compose -f compose.pilot-test.yml up -d --wait
$env:TEST_DATABASE_URL='postgresql+asyncpg://fogwrite:local_test_only@127.0.0.1:55439/fogwrite_test'
.\.venv\Scripts\python.exe -m pytest -q backend/tests -m "not live"
node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-ui.test.cjs
node scripts/fogwrite-auth.test.cjs
node scripts/fogwrite-smoke.cjs --offline
```

Use `FOGWRITE_NODE_MODULES` for cached frontend dependencies when needed. Normal builds use `npm run build`; the offline equivalent is `node scripts/build-frontend.cjs`.

Before release, test actual Alembic upgrade/current/check against a separate migration database, build the Linux Docker image, inspect CI, and verify the deployed commit and assets. `/ready` alone does not prove all schema columns are present. Clerk live sign-in, class authorization, end-to-end Gemini practice, and held-out scoring quality require separate acceptance/evaluation.
