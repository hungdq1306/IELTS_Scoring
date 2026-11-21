# FogWrite - IELTS Writing Studio

IELTS Academic Writing Task 2 practice, AI assessment and evidence-grounded personalized exercises. AI bands are estimates for learning, not official IELTS results.

## Run the correct application

| Mode | Entry point | Identity and storage | Purpose |
| --- | --- | --- | --- |
| Classroom pilot | `app.pilot:app` | Clerk + PostgreSQL/Neon | Roles, classes, quotas, durable queue, admin and audit |
| Local research/demo | `app.main:app` | Browser cookie + local SQLite | Research assessment options and benchmark APIs |

For the classroom pilot, follow [deployment and operations](backend/README_DEPLOY.md). Production is built with `backend/Dockerfile` and configured by `render.yaml`. For local Clerk development use `SETUP_CLERK.cmd` then `RUN_FOGWRITE_CLERK.cmd`. For the separate local demo use `RUN_FOGWRITE.cmd` (http://127.0.0.1:8000).

Keep API/database/Clerk secrets server-side. Configure `.env` from the relevant example without overwriting existing values: root `.env.example` covers research/demo settings; `backend/.env.example` covers pilot settings.

## Source and tools

| Path | Purpose |
| --- | --- |
| `frontend/src/fogwrite.jsx` | Sole React entry, authenticated shell and account-scoped browser state |
| `backend/app/pilot.py`, `routers/`, `services/`, `worker.py` | Pilot API, authorization, grading/practice and leased jobs |
| `backend/app/main.py`, `practice/` | Local research/demo API and shared practice schemas/validation |
| `backend/alembic/` | PostgreSQL schema migration history |
| `backend/benchmark/`, `src/data/`, `src/eval/` | Dataset preparation, benchmark/report CLIs and reproducibility |
| `artifacts/dataset_v1/` | Frozen anchors, splits and v1 evaluation evidence; seed anchors are used at runtime |
| `scripts/` | Build, browser tests and local launchers |
| `frontend/dist/` | Tracked preview bundle; Docker rebuilds it from source |

## Build and verify

```powershell
npm run build
node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-ui.test.cjs
node scripts/fogwrite-auth.test.cjs
node scripts/fogwrite-smoke.cjs --offline
```

For offline cached dependencies set `FOGWRITE_NODE_MODULES` and use `node scripts/build-frontend.cjs`. See [verification](docs/VERIFICATION.md) for backend/PostgreSQL tests, actual migration checks and known boundaries. Tests do not automatically establish live Clerk integration or AI scoring accuracy.

## Documentation

[Documentation index](docs/README.md), [architecture](docs/ARCHITECTURE.md), [UI](docs/FOGWRITE_UI.md), [product](PRODUCT.md), [demo/acceptance](docs/DEMO_GUIDE.md). Historical research and demo records are in [archive](docs/archive/README.md).

## Research reproduction

```powershell
python -m src.data.splitter --config configs/dataset_split.yaml
python -m src.eval.loo_audit --dry-run
python -m src.eval.ab_compare
```

Research dependencies are declared in root `requirements.txt`; pilot runtime/test dependencies are in `backend/requirements.txt` and `backend/requirements-dev.txt`. Benchmark reporting is available as `python -m benchmark.report` with `PYTHONPATH=backend`. Do not regenerate frozen holdout outputs merely to start or deploy the app.

## Historical v1 benchmark evidence

The results below belong to the frozen v1 experiments. The pilot defaults to experimental v2 and may apply teacher anchors/calibration offsets; these numbers do not measure those variants. See [final holdout report](artifacts/dataset_v1/final_holdout/final_holdout_report.md).

## Verified Benchmark Summary (`Baseline v0` → `Calibrated v1`)

Evaluated deterministically with **Clustered Bootstrap 95% CI (1,000 resamples by `prompt_cluster_id`)** and **SD Ratio (Wang & von Davier)**:

| Evaluation Split | Variant | Overall QWK [95% CI] | Micro-MAE | Macro-MAE | SMD (`\|SMD\| <= 0.15`) | SD Ratio (`[0.67, 1.50]`) | Adj `<= 0.5` | Mean Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **Examiner LOO-CV (13 folds)** | `v0_raw` | `0.7955` | `0.5769` | `0.3500` | `-0.4878` (FAIL) | `1.403` | `53.9%` | `6,985` |
| **Examiner LOO-CV (13 folds)** | **`v1_raw`** | **`0.9727`** | **`0.1923`** | **`0.2083`** | **`+0.1400` (PASS)** | **`0.984`** | **`100.0%`** | **`5,315`** |
| **Frozen Dev (173 essays, 33 clusters)** | `v0_raw` | `0.8443` [0.762, 0.885] | `0.3844` | `0.4668` | `-0.3786` (FAIL) | `0.967` | `88.4%` | `8,329` |
| **Frozen Dev (173 essays, 33 clusters)** | **`v1_raw`** | **`0.8771`** [0.829, 0.903] | **`0.3497`** | **`0.3414`** | **`-0.0926` (PASS)** | **`0.813`** | **`89.0%`** | **`5,532`** |
| **Locked Holdout (63 essays, 47 clusters)** | `v0_raw` | `0.7847` [0.692, 0.845] | `0.3968` | `0.4652` | `-0.3490` (FAIL) | `1.059` | `82.5%` | `8,324` |
| **Locked Holdout (63 essays, 47 clusters)** | **`v1_raw`** | **`0.8712`** [0.811, 0.910] | **`0.3413`** | **`0.3786`** | **`-0.0087` (PASS)** | **`0.864`** | **`92.1%`** | **`5,512`** |

- **Statistical Significance on Holdout (`v1_raw - v0_raw`):** $\Delta\text{QWK} = +0.0865$ (`95% CI [+0.0207, +0.1652]`, $p = 0.0060$ one-sided / $p = 0.0120$ two-sided), **5/5 dimensions pass `QWK >= 0.70` and `|SMD| <= 0.15`**, and **`-33.8%` token reduction**.

---
