# FogWrite UI and local preview

## Start

From the project root in PowerShell:

```powershell
.\scripts\start-fogwrite.ps1
```

Or, without invoking a script:

```powershell
$env:PYTHONPATH = 'backend'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The committed frontend/dist bundle requires no Node installation to preview. The backend reads the existing .env configuration. A configured Gemini key and network access are required for live grading and practice. No credentials are exposed in the frontend.

## Routes

Hash routes avoid server-side fallback requirements: landing, overview, topics, write, check, feedback, skills, history.

Writing starts only after a selected prompt is confirmed. The timer uses a persisted start timestamp, survives reload, and pauses on submission. At expiry the learner must explicitly continue before editing; extra time remains visible. A failed assessment preserves the draft and offers retry or a return to writing. Timings for completed assessments are restored in this browser using the submission ID.

Grounded annotations use unique exact matches against the immutable submitted text. Repeated or missing quotes are not arbitrarily assigned an offset. General criterion evidence is labelled neutrally; optional wording suggestions are separate from errors. Criterion evidence and detailed explanations remain available even if inline anchoring is ambiguous.

The criterion panel shows one of TR, CC, LR, GRA at a time. Practice opens as a dedicated screen. The selected criterion, source annotation and window scroll are retained while navigating back. A selected quote filters the available exercise batch by source overlap. Empty matches do not produce invented exercises; use Show all priority skills to see alternatives.

## Build

Normal development: install frontend/package.json dependencies, then `npm run dev` or `npm run build` inside frontend.

An alternative offline build is supplied for environments with esbuild and React already available:

```powershell
$env:FOGWRITE_NODE_MODULES = '<directory containing esbuild, react and react-dom>'
node scripts/build-frontend.cjs
```

The entry point is frontend/src/fogwrite.jsx. This alternative build is what produced the committed app.js/app.css. Do not run the older scratch build helper that points at main.jsx.

## Checks

`scripts/fogwrite-smoke.cjs` uses Playwright to check landing, sample highlight selection, criterion tabs, practice navigation, local draft persistence, timer expiry and extra-time editing, mobile overflow and browser exceptions. Set PLAYWRIGHT_MODULE and CHROMIUM_EXECUTABLE if these are in a shared runtime rather than installed locally.

FOGWRITE_OFFLINE_TEST=1 serves the built static files through Playwright request interception and stubs only health/history responses for browser checks. It does not claim live backend verification. In normal mode the script expects a real server on port 8000.

The host sandbox rejected socket access during this implementation. Live Gemini grading could not be confirmed here; run the start command in a normal terminal to test it. Existing backend regression checks and in-process diagnostics were attempted separately; record only completed results, not hanging runs.
