# IELTS Writing Studio

Automated IELTS Academic Writing Task 2 assessment and targeted practice platform built with **FastAPI**, **React**, and **Google Gemini** (`gemini-3.5-flash-lite`), calibrated to the **May 2023 official IELTS Writing Band Descriptors** using an **8-anchor stratified examiner benchmark (`V1_STRATIFIED`)**.

---

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

## Repository Structure

| Path | Purpose |
|---|---|
| `src/data/` | Deterministic dataset cleaning, May 2023 IELTS rounding, quality tiering (`tiering.py`), TF-IDF cosine cluster-disjoint splitting & audit reporting (`splitter.py`) |
| `src/eval/` | Psychometric AES metrics (`metrics.py`), Prompt `v1` stratified anchors (`prompt_v1.py`), 13-fold Examiner LOO-CV (`loo_audit.py`), Dev/Holdout runners (`dev_baseline.py`, `holdout_final.py`, `ab_compare.py`) |
| `configs/dataset_split.yaml` | Centralized split thresholds (`seed: 42`, `max_prompt_sim: 0.60`), schema mappings, and tail-protection settings |
| `artifacts/dataset_v1/` | Frozen `seed.jsonl` (15), `dev.jsonl` (173), `holdout.jsonl` (63), `audit_report.md`, and complete `baseline_v0/`, `candidate_v1/`, `final_holdout/` evaluation logs |
| `backend/app/` | FastAPI service, `task2-v1-calibrated` rubric (`grading/rubric.py`), `V1_STRATIFIED` 8-anchor loader (`grading/lecturer.py`), evidence/grammar grounding (`grading/task2.py`), Gemini provider (`providers/gemini.py`), and Personalized Practice engine (`practice/`) |
| `frontend/` | React live demo UI (`src/main.jsx`, `src/practice.jsx`, `src/detailed.jsx`, `src/shared.jsx`, `src/api.js`) + prebuilt static bundle (`dist/`) served directly by FastAPI |
| `tests/`, `backend/tests/` | Automated dataset integrity, leakage, psychometric metric, and FastAPI E2E wiring tests |
| `docs/` | Architecture, Demo Guide, and Personalized Practice specifications |

---

## Quick Start (Live E2E Demo)

### 1. Install Dependencies & Configure API Key

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY=<your-google-ai-studio-key>
```

Verify Gemini model access:

```powershell
$env:PYTHONPATH = "backend"
python -m app.providers.gemini
```

### 2. Run the Web Application

```powershell
$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** (FastAPI serves the prebuilt `frontend/dist/` bundle; API docs are at **http://127.0.0.1:8000/docs**).

- **Default Assessment Method:** `Calibrated v1 · 8 Examiner Anchors (5.0-9.0)` (`V1_STRATIFIED`), using Prompt `v1` + 8 stratified examiner-verified anchors from `artifacts/dataset_v1/seed.jsonl`.
- **Other Options:** `Rubric v1 Only` (`FS0`) and `Lecturer · 5-Shot (5.0-8.0)` (`FS5_FULL`).
- **Personalized Practice:** After grading an essay, open **Practice Your Mistakes** to generate evidence-grounded exercises, hints, and paragraph revision checks.

*(Optional frontend hot-reload if Node.js 20+ is installed: `cd frontend && npm install && npm run dev`, then open http://127.0.0.1:5173.)*

---

## Reproducing Dataset Splitting, Evaluation & Tests

### Run Automated Offline Test Suite (42 Tests, Zero API Calls)

```powershell
python -m pytest -v -m "not live"
```

### Rebuild `artifacts/dataset_v1/` Deterministically

```powershell
python -m src.data.splitter --config configs/dataset_split.yaml
```

### Run Evaluation Pipelines

```powershell
# 13-Fold Examiner LOO-CV (zero-cost dry run or live)
python -m src.eval.loo_audit --dry-run
python -m src.eval.loo_audit --live --prompt-version v1 --out-dir artifacts/dataset_v1/candidate_v1

# Frozen Dev & Final Holdout reports
python -m src.eval.ab_compare
```

---

## Further Documentation

- [System Architecture](docs/ARCHITECTURE.md)
- [Standalone Web Specification (V2)](docs/SPEC_V2_STANDALONE_WEB.md)
- [Live Demo Guide](docs/DEMO_GUIDE.md)
- [Dataset Audit Report](artifacts/dataset_v1/audit_report.md)
- [Final Holdout Evaluation Report](artifacts/dataset_v1/final_holdout/final_holdout_report.md)
- Personalized Practice: [Research](docs/PERSONALIZED_PRACTICE_RESEARCH.md) · [Architecture](docs/PERSONALIZED_PRACTICE_ARCHITECTURE.md) · [API](docs/PERSONALIZED_PRACTICE_API.md) · [Evaluation](docs/PERSONALIZED_PRACTICE_EVALUATION.md) · [Demo](docs/PERSONALIZED_PRACTICE_DEMO.md)
