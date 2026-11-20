# FogWrite UI and preview

## Run

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = 'backend'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Restart an already-running backend after updating this version so the new page URL fallback and cache headers take effect. The committed frontend/dist bundle does not need Node to preview.

## Routes

| Screen | URL |
| --- | --- |
| Landing | / |
| Topic library | /topics |
| Timed writing | /practice |
| Assessment overview | /assessment |
| Criterion detail | /assessment/task-response, /assessment/coherence-cohesion, /assessment/lexical-resource, /assessment/grammatical-range-accuracy |
| Skill practice | /skill-practice |

Additional workspace routes are /overview, /check and /history. Legacy hash links continue to work. Known page URLs fall back to the React entry point; missing API and image URLs remain errors.

The landing Sample feedback button opens a labelled illustrative assessment without replacing the current draft. Criterion rows navigate to their detail URLs, and the practice action opens a labelled sample exercise. Sample responses demonstrate the interface and do not call Gemini. Live assessments and generated practice use the original backend endpoints and cookie-owned submissions.

## Writing and persistence

The timer uses persisted timestamps and stops on submission. Continuing after expiry requires an explicit choice, which survives reload. Failed requests preserve the draft. Assessment rendering uses the submitted snapshot rather than editable text. History asks before replacing an unfinished draft and locks navigation during restoration.

The essay remains plain text for grading. B/I/U alter the editor display; list controls insert plain-text bullets or numbers at the selected lines. Typography controls do not add hidden markup to an essay. Browser-local drafts and submitted text keep the same API contract.

Sign in is present in the design, but account authentication is not implemented in this pilot. Its dialog explains that the current browser session owns the saved work; it does not claim to sign in or synchronize accounts.

## Build

Inside frontend, use the normal package install and Vite build. Alternatively:

```powershell
$env:FOGWRITE_NODE_MODULES = '<node_modules containing esbuild, react, react-dom and lucide-react>'
node scripts/build-frontend.cjs
```

The entry point is frontend/src/fogwrite.jsx. The offline build copies public assets and stamps JS/CSS references with a content hash. Vite uses its native hashed filenames. The HTML metadata fogwrite-ui=screen-design-01 identifies this implementation.

## Verification

```powershell
node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-ui.test.cjs
```

These checks cover grounding, draft normalization, all seven transparent PNGs, placeholder behavior, absence of hand-coded SVGs in source, sidebar composition, all six screen component structures, page routes and copied build assets.

The browser checker captures all six screens at 1440x900 and 1280x800 and checks image loading, a missing-image fallback, horizontal overflow, mascot bounds, navigation, draft isolation and real client grading/practice contracts with fixture responses:

```powershell
$env:FOGWRITE_OFFLINE_TEST = '1'
node scripts/fogwrite-smoke.cjs
```

In frontend, npm run test:ui runs the same offline check. Install the declared dev dependencies and run npx playwright install chromium once on a normal development machine. Set PLAYWRIGHT_MODULE and CHROMIUM_EXECUTABLE for shared dependencies when necessary. Screenshots go to .cache/ui-checks, or FOGWRITE_SCREENSHOT_DIR. Offline mode intercepts static requests and uses explicit test responses; it does not verify live Gemini accuracy.

In this implementation session, full Chromium failed to start, but the installed Chromium headless shell successfully completed all six screens at both sizes (12 screenshots), image-fallback checks, navigation, draft persistence and grading/practice client-contract checks. The source reference image download failed, and Google Fonts are blocked in offline mode, so exact pixel comparison with the reference is not claimed. No live Gemini requests were made.
