# System Architecture

## 1. End-to-End Web & Grading Flow

- **Frontend (`frontend/`):** React 19 UI served directly from `frontend/dist/` by FastAPI (or proxied via Vite on `:5173` during development). Users submit a Task 2 question and essay with a selected assessment method (`V1_STRATIFIED`, `FS0`, or `FS5_FULL`).
- **Grading Service (`backend/app/grading/`):**
  - Applies **May 2023 official IELTS Writing Task 2** descriptors (`rubric.py`, `PROMPT_VERSION = "task2-v1-calibrated"`).
  - **`V1_STRATIFIED` mode (`lecturer.py`):** Injects 8 stratified examiner-verified calibration anchors spanning Bands 5.0–9.0 (`lecturer_05`, `04`, `02`, `06`, `07`, `09`, `10`, `13`) loaded from `artifacts/dataset_v1/seed.jsonl` with criterion-level examiner calibration cues and overlap protection (`fewshot.py`).
  - **Structured Output & Grounding (`schemas.py`, `detailed.py`, `task2.py`, `ownership.py`):** Gemini returns native JSON conforming to `DetailedModelGrade`. The backend computes the overall band via official `ROUND_HALF_UP` to 0.5 increments, rejects leaked prompt quotes, and strips any ungrounded essay quotes or grammar edits before returning the response.
- **Provider & Rate Pacing (`backend/app/providers/gemini.py`):** Shared SQLite request ledger (`results/_quota.sqlite3`) enforces RPM pacing, daily request budget, and bounded exponential-backoff retries.
- **Personalized Practice (`backend/app/practice/`):** Generates evidence-grounded targeted exercises, progressive hints, and paragraph revision feedback linked to the evaluated submission (`results/_practice.sqlite3`).

## 2. Dataset & Psychometric Evaluation Pipeline (`src/`)

- **Cleaning & Tiering (`src/data/tiering.py`):** Parses raw dual-rater (`862` essays) and examiner-verified (`13` essays) inputs, strips contaminated HTML/boilerplate scripts, normalizes scores to 0.5 steps, and classifies `quality_tier` (`examiner_verified`, `max2_half`, `max3_half_only`, `rejected`).
- **Cluster-Disjoint Splitting (`src/data/splitter.py`):** Uses deterministic TF-IDF `(1,2)`-gram cosine similarity clustering (`threshold = 0.60`) and tail-protected optimization (`seed = 42`) to guarantee zero essay overlap, zero cluster overlap, `100% max2_half` purity in `Holdout`, and all 13 `examiner_verified` essays in `Seed`.
- **Psychometric Evaluation (`src/eval/`):** Computes QWK (`0..18` half-band classes), Micro-MAE, RMSE, Macro-MAE, SMD, SD Ratio (`[0.67, 1.50]`), Exact/Adjacent agreement, tail-stratum bias, and Clustered Bootstrap 95% CIs (`1,000` cluster resamples) across 13-fold Examiner LOO-CV, Frozen Dev, and Locked Holdout.
