# Local demo cleanup and branch

Verified on 2026-11-24 in `feat/fogwrite-tour-local-demo`.

## Removed from the workspace

21 regenerable directories (20,458,805 bytes, approximately 19.5 MiB) were moved
to Windows Recycle Bin, so they remain recoverable. This cleans the workspace;
it does not reclaim disk space until the Recycle Bin is emptied.

- Old Playwright temporary profiles and artifact directories.
- Temporary pytest output under `.cache/pytest-of-unknown`.
- Old `.cache/tour-dev` and `.cache/tour-test-dist` bundles.
- Python `__pycache__` directories in source, tests and benchmark packages.

The root `.pytest_cache` was conservatively retained by the active-reference check.
Permanent recursive deletion was rejected by automatic review; the recoverable
Recycle Bin operation succeeded.

The ignored `.cache/cleanup-safety/` folder contains the working-tree patch,
untracked-source backup and exact cleanup manifest. Source edits visible before
the branch change were preserved in existing commit `2648fc3`; they were not
discarded or replaced during cleanup.

## Retained after reference checks

- `frontend/src/`, tour/help components and browser tests: imported or used by
  package scripts.
- `frontend/dist/`: used by the no-Node preview and browser-test fixtures.
- Build/preview launchers: referenced by npm scripts, CI or documentation.
- Dependencies and offline dependency caches: needed for builds/tests/fallback.
- `.env`, database directories, dataset anchors, EssayJudge data, benchmark
  outputs and gold drafts: source configuration, runtime state or research evidence.
- Archived documentation: linked from the documentation index.

UI-only tour testing does not require the real FastAPI/Clerk/Gemini backend or
research benchmark execution. These components are retained for their other uses.
`.dockerignore` additionally excludes Python virtual environments and the isolated
`benchmarks/` tree from the production Docker context. The Dockerfile only copies
frontend/backend source and the required frozen calibration seed; none of those
runtime inputs are excluded by these additions.

## Running demo

- Student: <http://127.0.0.1:5174/?tour=student>
- Teacher: <http://127.0.0.1:5174/?tour=teacher>
- Frontend: Vite on 5174; read-only preview API on 8001.

This demo does not call Gemini, spend grading credits or change real classes.
See [interactive-tour instructions](INTERACTIVE_TOUR.md) to restart the two servers.

Python caches may reappear automatically while other application/tests run. The
cleanup manifest records the directories recycled at cleanup time, not a promise
that generated cache directories will stay absent.

Post-cleanup verification: tour TypeScript check and 19/19 unit/UI tests passed;
Student/Teacher launch URLs, class deep link and preview API returned HTTP 200.

The post-cleanup live Playwright tour suite also passed for Student and Teacher
on desktop/mobile, including input-pause, account-scoped completion, draft
preservation, reduced motion and autoplay. No tour mutation/local HTTP errors.
