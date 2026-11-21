# RBAC and AI v2 upgrade

Implemented against `Pasted markdown.md` (21 November 2026).

## Behavior

- New accounts remain students. Trusted operator `app.manage grant-role` bootstraps the first administrator; subsequent role, suspension and bonus-credit changes use authenticated `/api/admin/users` and are audited. The last active admin is protected.
- Unenrolled students get zero credits and `CLASS_ENROLLMENT_REQUIRED`. Active students get the maximum quota across active classes plus bonus credits. Defaults: student 3, TA 5, teacher 20, admin 50.
- Credits reset at midnight Asia/Ho_Chi_Minh. Completed, queued and scoring submissions consume credits; permanently FAILED essay jobs release student credits automatically. Failed practice does not refund the successful essay assessment. Global cap counts all admissions, including failures, to protect costs.
- Admission is serialized with a PostgreSQL row lock before counting/inserting. Idempotent retries recover existing jobs without charging again. SQLite remains a local adapter only.
- Staff also select an active class for essay grading. Teachers/admins can create their own class first. TAs may review only assigned classes and cannot override teacher scores or access invite codes.
- New invite codes are eight uppercase unambiguous letters/digits. Case and outer whitespace are normalized. Invite codes and links are available only to owners/admins. Legacy hashed-only invites continue to work; regenerate once to enable a retrievable dashboard code. Rotation invalidates previous invites immediately. Removed students can rejoin using a valid invitation, as specified by this plan.
- Teacher APIs include roster, removal, TA assignment, essay review, overrides, class activation/quota edits, anchors, templates and prompts. Existing routes remain usable.
- Account, privacy consent, My Classes and admin screens use the application account menu. No top-of-page technical account banner is injected. `/join?code=...` opens the join page and preserves the invitation through sign-in.

## AI variant

`app/grading/v2.py` defines an evidence-first structural audit followed by short rubric evidence summaries and half-band scores. It includes objective paragraph/word/repetition telemetry, anti-length-bias instructions, CC/GRA separation and explicit half-band rules. These are concise observable assessments, not a request to expose private model chain-of-thought.

The scorer adapts v2 into the existing detailed frontend result contract, filters ungrounded sentence annotations, retains raw scores, applies teacher plus global criterion offsets, clips/rounds half bands and computes Overall on the server. Teacher reference selection retains one essay per available overall band from up to 100 active anchors, rather than placing 100 essays in every prompt. Baseline stratified references remain the fallback. Configuration is snapshotted per submission.

Default active prompt is `v2`; admin settings can select `v1` for new submissions. Existing queued jobs retain their original snapshot. V1 benchmark results do not establish v2 accuracy; evaluate v2 independently on held-out teacher essays before making accuracy claims.

Provider usage records cover grading and practice responses after this migration without essay text or identities. Admin overview exposes tokens, queue depth, role counts, recorded/unknown calls and pricing coverage. To enable USD cost estimates, set `model_prices_usd_per_million` to `{ "EXACT_MODEL_NAME": {"input": 0.0, "output": 0.0} }` using verified account/model prices. Empty pricing yields unknown cost; a zero price must only be configured when appropriate for the provider account. Unknown usage, interrupted calls and provider billing cannot be reconciled exactly from this ledger.

## Deployment order

1. Commit/push source, generated frontend bundle and migration together. Stop incoming grading requests during migration/deploy if needed.
2. From the repository root with the intended Neon migration URL configured:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

3. Deploy the matching code on Render. Check `/ready`, sign in with two accounts, create/join a class and test quota, rotation and scope on the deployed app.
4. Bootstrap the first admin with its verified Clerk identity:

```powershell
.\.venv\Scripts\python.exe -m app.manage grant-role --clerk-user-id "user_REPLACE_WITH_VERIFIED_ID" --role admin
```

Do not run the new code against an unmigrated database. Migration is additive and preserves existing classes/memberships. Existing memberships with no recorded join timestamp retain `joined_at=0` (unknown historical date).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -v backend/tests/test_rbac_and_ai_v2.py backend/tests/test_concurrency_and_guardrails.py
```

Use an isolated database named `fogwrite_test` for PostgreSQL verification via `TEST_DATABASE_URL`; the tests refuse to reset other PostgreSQL database names. Never point tests at production. The suite mocks Gemini and does not measure scoring accuracy.

Frontend can be rebuilt with `npm run build`. For the offline workspace cache:

```powershell
$env:FOGWRITE_NODE_MODULES = Join-Path (Get-Location) ".cache/pilot-ui-deps/node_modules"
node scripts/build-frontend.cjs
```

Workspace verification: offline frontend bundle built successfully; Python compilation and offline Alembic SQL generation passed. Synchronous telemetry/schema/rounding/guardrail tests passed. Async integration tests are blocked at Windows `asyncio` event-loop socketpair creation in this sandbox, before application requests execute; run the full suite in an environment permitting local sockets or Linux CI.

Release preparation on 21 November 2026: production Neon migration `0002_rbac_v2` applied successfully in one transaction. Existing users, classes, prompts, eight anchors and three templates remain present. AI v2 sentence annotations now carry a criterion and feed grounded frontend highlights. The mocked scorer adapter smoke check passed without network calls. The code release to Render is pending publication to GitHub: local Git HTTPS fails DNS resolution for `github.com`; the current Render live commit is still `cf97fb4`. Do not treat the database migration as proof that the new application has been deployed.
