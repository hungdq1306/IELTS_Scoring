# FogWrite: revised implementation plan

Reviewed against `feat/fogwrite-tour-local-demo`, 2026-11-24. Preserve existing work.

## Corrections to the supplied plan

- Persisted success is `COMPLETED`; `DONE` is an admin display label. Keep the existing flat grade response contract.
- Cache eligibility requires the same owner, active class, resolved prompt, full essay, grading model/thinking budget and complete configuration snapshot (teacher anchors/style/offsets, global offsets, prompt revision and feedback language). A prompt-version-only hash would serve stale grades. Normalize CRLF only; do not collapse paragraphs or internal whitespace because grounding and paragraph structure matter.
- Check consent, membership and input validity before reuse, but enforce credit/queue admission only on a miss. Keep request idempotency; also reconnect identical in-flight work under the existing per-user submission lock. Failed work is never reused. Old rows with null hashes are intentionally cache misses; do not invent historical grading context.
- Practice answers already exist in `PracticeSet.draft_answers` and immutable `Job.payload.answers`. Derive canonical answer hashes from these instead of adding redundant per-item version columns. Return feedback only for matching answers. Store hint use at submission time; retain timestamp-based fallback for historical jobs. Order first attempts by submission time, not completion time.
- Exercises are embedded JSON, not individual ORM rows. Add an indexed exercise-to-submission reference table, backfill existing ready sets, populate it atomically on generation, and preserve owner-only authorization. No new teacher/TA rights are needed.
- Keep `prompt`/`essay` API names. Failed detail loading returns content independently of grading, with a safe error code/message, refund status and Edit & Resubmit flow.
- Student routes already follow overview → classes → combined editor → assessment → practice → history. Preserve this order, make prompt/essay/submit actions explicit, and use an 8-second auto dwell after the final cursor demonstration settles; pause on hover, input or hidden tabs. Reduced-motion remains manual.
- Use module-object mocks and a network-denying test guard. Run unittest discovery with `-t .` so relative imports resolve. CI needs separate Task 1 dependencies as well as the test command.

## Delivery and validation

1. Migration for nullable indexed content hash, submission request aliases (so reconnect/cache hits retain idempotency), and exercise references; no production DB changes during implementation.
2. Regression coverage for cached/edited/cross-user/failed/context-changed submissions, concurrency and quota-free cache hits; answer/result snapshots; failed recovery; exercise 101 and authorization; chronological hint metrics.
3. Tour pacing, preview order and browser checks at desktop/mobile sizes.
4. Backend non-live suite, Task 1 pytest and unittest with network blocked, frontend unit/API/browser suites, tour typecheck, Vite and offline builds, PostgreSQL offline migration SQL and isolated migration checks where available.
5. Report actual counts and local demo URL. No Gemini calls are needed; no human-verified Task 1 accuracy claims.
