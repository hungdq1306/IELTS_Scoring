# Single-class enrollment and post-QA implementation plan

Reviewed against Pasted text(3).txt on 21 November 2026. This document records the revised requirements implemented in this checkout; it is not a deployment receipt.

## Corrections to the proposed plan

1. The actual table is `class_memberships`. Keep `active` as the indexed state; `left_at` and `removed_at` distinguish voluntary leave from staff removal. API `status` is derived: ACTIVE when active, LEFT when left_at exists, REMOVED otherwise. This avoids independently writable active/status values.
2. One active **student enrollment** occupies a slot even when its classroom is inactive. Classroom deactivation blocks submissions, not silently drops enrollment. Auth classes expose that inactive membership so the student can explicitly leave it. Staff can have multiple memberships.
3. The partial unique index uses membership role and active. PostgreSQL triggers synchronize the role with `users.role`, including direct SQL role changes. HTTP/CLI role changes also validate before demotion. Never silently remove an enrollment to make migration pass: migration aborts if existing students have multiple active memberships.
4. Browser JSON is not authenticated Clerk profile evidence. Store `reported_full_name`/`reported_email` separately, label effective values `self_reported`, prefer verified existing fields, and never use them for authorization, account matching, invitations, or email delivery. Signed JWT/custom claims or Clerk Backend API remain authoritative. UTF-8 travels in JSON, never identity headers.
5. LEFT preserves the owner's History, assessment and practice access, including polling an already admitted job. REMOVED retains the existing access-revocation policy. The class teacher can still review class submissions. Retention rules continue to apply; preservation is not indefinite storage.
6. Cooldown is 24 elapsed hours after the latest voluntary leave or staff removal; removal uses removed_at, not a nonexistent left_at. Invite self-rejoin after removal is blocked. Explicit staff reinstatement can override cooldown/removal, but cannot create a second active student enrollment.
7. Global user-scoped credits already existed: preserve that accounting across leave/join. New essay submissions require an active classroom. Closing enrollment only prevents invitations; existing students keep access.
8. Class resolution continues to accept a Clerk user ID for its account-scoped stored preference, then uses the first active class as fallback. The parent submit handler passes that resolved class_id; pilotApi no longer repeats auth/me before submission. Backend membership checks remain authoritative.

## Implementation

- Migration `0004_single_class`: enrollment_open, leave/removal timestamps, unique index, role-sync triggers and separate reported profile fields. Inactive historical memberships become removed (timestamp 0 means unknown historical time).
- `enrollment.py`: per-user serialized join/leave/role policy, structured conflict/cooldown errors and staff reinstatement handling.
- Pilot routes: own-only display profile PATCH, join and leave audit, LEFT history/ownership, class context.
- Teacher/admin/CLI: enrollment toggle, removal timestamps, role conversion and source-aware display/search. Admin profile sync without a secret returns an explicit explanation.
- Frontend: deduplicated auth refresh/profile bootstrap; shared class fallback and explicit class_id; leave dialog, enrollment toggle, zero-class submission blocking; search reset/empty state; no-op admin save blocking; operator/membership audit options.

## Validation and release gates

- Unit tests use a real SQLite unique index and validate Unicode/profile provenance. HTTP integration tests cover join races, cooldown, quota continuity, original jobs, removal, locks and profile privilege isolation.
- Browser fixtures cover all existing role/viewport cases plus leave/cancel/confirm, the zero-class submit block, roster search reset and admin no-op/audit options. Mocks do not establish live Clerk integration.
- The exact Alembic 0004 SQL was applied only to the existing isolated Neon branch `release-b38e85a-schema-check`. Its PostgreSQL index/triggers rejected a spoofed student member role and a two-class teacher demotion; the teacher retained two classes and the student one.
- The restricted local runtime cannot complete asyncio-backed HTTP tests (it stalls before requests). Run the full backend suite on isolated PostgreSQL and the real migration upgrade/check separately before publishing. Do not apply 0004 to production or deploy this checkout merely because the previous release passed.

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://fogwrite:local_test_only@127.0.0.1:55439/fogwrite_test'
.\.venv\Scripts\python.exe -m pytest -q backend/tests -m "not live"
```

For a database already at 0003 on the isolated migration test instance, run Alembic upgrade head then check using its direct URL. Duplicate-enrollment preflight failures must be resolved explicitly by an operator. Rolling back columns would remove leave/removal metadata; do not automatically downgrade a live database.


## Recorded local validation

48 synchronous backend cases passed, including the new actual-index and Unicode/provenance regressions. Frontend build `b384bd8cc108` and 19 model/component cases passed. All 20 role/viewport browser cases, account-switch draft/timer and pending-restore/History regressions, expanded leave/search/admin cases, and offline six-screen smoke passed. The user subsequently reported 89 passed, 1 live test deselected for the complete backend offline suite in external PowerShell after restoring the isolated PostgreSQL test connection. This is user-reported execution, not an agent-runtime full run. Actual Alembic upgrade/check and live acceptance remain separate release checks.
