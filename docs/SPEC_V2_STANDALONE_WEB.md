# `SPEC_V2_STANDALONE_WEB.md`
## Standalone Teacher-Personalized IELTS Writing Task 2 Web Application

- **Target Scale:** ~100 active students (`YP03`, `YP04`, `YP05`, plus self-paced learners), handling end-of-class bursts of **35–40 simultaneous submissions**.
- **Stack:** React 19 + TypeScript + Vite + Tailwind CSS + shadcn/ui (**Cloudflare Pages / Vercel**) · Python 3.11+ FastAPI single `Dockerfile` (**Render / Koyeb / VPS**) · **Supabase** (PostgreSQL 16 + Auth + RLS + `FOR UPDATE SKIP LOCKED`) · **Google Gemini** (`@google/genai` / `google-genai` SDK).
- **Verified Baseline (`IELTS_Scoring` `v1`):** `0.8771 QWK` / `0.3414 Macro-MAE` on Frozen Dev (173 essays); `0.8712 QWK` / `-0.0087 SMD` / `92.1% Adj <= 0.5` on Locked Holdout (63 essays); `~5,532 tokens/essay`; `~5.5–6.0s` mean latency.

---

## Table of Contents
1. [System Architecture & High-Concurrency Execution Model](#1-system-architecture--high-concurrency-execution-model)
2. [Database Schema (PostgreSQL / SQLAlchemy + Alembic)](#2-database-schema-postgresql--sqlalchemy--alembic)
3. [Module 1 — Teacher-Personalized AES & Error Correction Engine](#3-module-1--teacher-personalized-aes--error-correction-engine)
4. [Module 2 — Format-Locked Personalized Practice Generator](#4-module-2--format-locked-personalized-practice-generator)
5. [REST API Contract (FastAPI)](#5-rest-api-contract-fastapi)
6. [Frontend UX & Role-Based Views (React + Tailwind)](#6-frontend-ux--role-based-views-react--tailwind)
7. [Guardrails, Security & Anti-Abuse Controls](#7-guardrails-security--anti-abuse-controls)
8. [Deployment Architecture, Roadmap & Cost Analysis](#8-deployment-architecture-roadmap--cost-analysis)

---

## 1. System Architecture & High-Concurrency Execution Model

### 1.1. End-to-End Architecture

```text
[React 19 SPA (Cloudflare Pages / Vercel)]
   │  Supabase Auth (JWT) / Optional YP Portal Signed Deep-Link
   ▼
[FastAPI Single Container (Python 3.11+)]
   ├─ HTTP Layer (REST API + Pydantic v2 + $0 Input Gates)
   │     └─ POST /api/submissions -> Insert status="QUEUED" (<100ms) -> 202 Accepted
   │
   ├─ In-Process asyncio Worker Pool (Semaphore + Configurable 10–12 RPM Pacer)
   │     ├─ Claims jobs atomically: SELECT ... FOR UPDATE SKIP LOCKED
   │     ├─ Stage 1: Personalized Scoring + Sentence Annotations (google-genai)
   │     │     ├─ Recomputes IELTS Overall (ROUND_HALF_UP) + Verbatim Grounding
   │     │     └─ Status -> GENERATING_PRACTICE
   │     └─ Stage 2: Decoupled Format-Locked Practice Generator (google-genai)
   │           └─ Status -> DONE (or FAILED with retryable backoff)
   ▼
[Supabase PostgreSQL 16 + Auth + RLS]
```

### 1.2. Handling 35–40 Simultaneous Student Submissions (Zero External Broker)
No Redis or Celery is needed for ~100 active students:
1. **Non-Blocking Submission (`< 100ms`):** `POST /api/submissions` runs `$0` validation gates, inserts a row in `submissions` with `status = 'QUEUED'`, and returns `202 Accepted` `{ submission_id, status: "QUEUED", queue_position }`.
2. **In-Process `asyncio` Worker Pool (FastAPI `lifespan`):**
   - Spawns `N = 2–3` async worker coroutines inside the FastAPI process gated by a shared `asyncio.Semaphore` and sliding-window RPM rate limiter (`10–12 RPM`, configurable via env).
   - Each worker polls PostgreSQL using `SELECT id FROM submissions WHERE status = 'QUEUED' ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1` (waking immediately via `asyncio.Event` on local submit or every `1.5s` fallback).
   - **State Machine:** `QUEUED` → `SCORING` → `GENERATING_PRACTICE` → `DONE` (or `FAILED` after 3 exponential-backoff retries).
   - **Stale Lock Recovery:** On startup and every 60s, resets any job stuck in `SCORING` or `GENERATING_PRACTICE` with `locked_at < NOW() - INTERVAL '120 seconds'` back to `QUEUED` (if `attempts < 3`).
3. **Burst Timing & Polling UX:** Under `10–12 RPM` (`~5–6s/call`), a 40-student end-of-class burst drains completely in ~3.5–4 minutes. The React SPA polls `GET /api/submissions/{id}/status` every `2.5s` and renders live queue position (`"Position #7 in queue (~40s)"`).

---

## 2. Database Schema (PostgreSQL / SQLAlchemy + Alembic)

All tables reside in Supabase PostgreSQL with Row-Level Security (RLS) enabled for direct client safety and FastAPI service-role access:

| Table | Core Columns & Constraints | Purpose |
|---|---|---|
| **`users`** | `id (UUID PK, matches auth.users)`, `email (UNIQUE)`, `full_name`, `role ('student'\|'ta'\|'teacher'\|'admin')`, `external_portal_id`, `created_at` | Core identity & RBAC synced with Supabase Auth / YP Portal handoff |
| **`classes`** | `id (UUID PK)`, `name` (e.g., `YP03`, `YP04`, `YP05`), `join_code (UNIQUE)`, `teacher_id (FK -> users.id)`, `created_at` | Cohort isolation and self-serve class enrollment |
| **`class_memberships`** | `id (UUID PK)`, `class_id (FK)`, `user_id (FK)`, `joined_at`, `UNIQUE(class_id, user_id)` | Many-to-many student-to-class mapping |
| **`prompts`** | `id (UUID PK)`, `source ('CURATED_BANK'\|'STUDENT_CUSTOM')`, `task_type`, `topic_tag`, `prompt_text`, `is_published (BOOL)`, `created_by (FK -> users.id)`, `created_at` | Curated teacher prompt bank + student custom prompts |
| **`submissions`** | `id (UUID PK)`, `user_id (FK)`, `prompt_id (FK)`, `attempt_number (INT)`, `essay_text`, `word_count (INT)`, `status ('QUEUED'\|'SCORING'\|'GENERATING_PRACTICE'\|'DONE'\|'FAILED')`, `attempts (INT)`, `locked_at`, `error_message`, `prompt_version`, `tokens_used (INT)`, `latency_ms (INT)`, `created_at` | Durable essay & revision history + PostgreSQL job queue (`INDEX(status, created_at)`) |
| **`assessments`** | `id (UUID PK)`, `submission_id (UUID UNIQUE FK -> submissions.id)`, `tr_score`, `cc_score`, `lr_score`, `gra_score`, `overall_score`, `criterion_feedback_json (JSONB)`, `sentence_annotations_json (JSONB)`, `top_weaknesses_json (JSONB)`, `validation_warnings_json (JSONB)`, `teacher_override_json (JSONB)`, `reviewed_by (FK -> users.id)`, `reviewed_at` | Stage 1 AI scores (`0.5` steps) + coaching feedback + optional Teacher override without mutating AI baseline |
| **`practice_sets`** | `id (UUID PK)`, `submission_id (UUID UNIQUE FK -> submissions.id)`, `user_id (FK)`, `exercises_json (JSONB)`, `student_answers_json (JSONB)`, `score_summary_json (JSONB)`, `completed_at`, `created_at` | Stage 2 format-locked exercises & student attempt persistence |
| **`teacher_anchors`** | `id (UUID PK)`, `code (UNIQUE)`, `prompt_text`, `essay_text`, `word_count`, `tr_score`, `cc_score`, `lr_score`, `gra_score`, `overall_score`, `examiner_cue`, `split_role ('SEED'\|'DEV'\|'HOLDOUT')`, `is_active (BOOL)` | Stores Teacher Nguyên's stratified calibration anchors |
| **`exercise_templates`** | `id (UUID PK)`, `format_type ('INFORMAL_TO_FORMAL'\|'TARGETED_ERROR_CORRECTION'\|'GUIDED_FILL_IN_BLANKS')`, `title`, `sample_json (JSONB)`, `version`, `is_active (BOOL)` | Stores Teacher Nguyên's 3–5 format-locked sample templates per exercise type |

---

## 3. Module 1 — Teacher-Personalized AES & Error Correction Engine

### 3.1. Personalization Without Fine-Tuning
Directly reuses `backend/app/grading/rubric.py` (`SYSTEM_PROMPT` v1) and `src/eval/prompt_v1.py`:
1. **Teacher Style & Strictness Profile:** Injects Teacher Nguyên's rubric rules (e.g., strictness on off-topic generalization, balanced 2-part prompt coverage, coaching tone/register) alongside May 2023 official rules (no artificial `8.0` ceiling, rare slips allowed at Band 9, no double-penalization of `CC` for grammar).
2. **`8–10` Stratified Teacher Anchors (`teacher_anchors` where `split_role = 'SEED'` & `is_active = true`):** Covers Bands `4.5–8.5+` with concise `examiner_cue` summaries.
3. **Per-Criterion Calibration Offsets:** Server applies frozen `Dev`-learned additive offsets (`offset_TR`, `offset_CC`, `offset_LR`, `offset_GRA`) only if `|SMD| > 0.15`, clamps `[0.0, 9.0]`, rounds to `0.5`, and computes `overall_score` via `ROUND_HALF_UP` (`.25 -> .5`, `.75 -> +1.0`) + displays **`± 0.5` band margin**.

### 3.2. Pydantic v2 Output Schema (`AssessmentOutput`)
Preserves the `_scores_last` schema-ordering invariant from `backend/app/providers/gemini.py`:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

ErrorType = Literal["grammar_syntax", "lexical_collocation", "coherence_cohesion", "task_response"]

class SentenceAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_sentence: str = Field(..., min_length=1, max_length=600)
    error_type: ErrorType
    explanation: str = Field(..., min_length=1, max_length=500)
    minimal_fix: str = Field(..., min_length=1, max_length=600)
    band_upgrade: str = Field(..., min_length=1, max_length=600)

class WeaknessSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_type: ErrorType
    pattern_label: str = Field(..., min_length=1, max_length=120)
    coaching_summary: str = Field(..., min_length=1, max_length=400)

class CriterionFeedbackText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_response: str = Field(..., min_length=1, max_length=1200)
    coherence_cohesion: str = Field(..., min_length=1, max_length=1200)
    lexical_resource: str = Field(..., min_length=1, max_length=1200)
    grammatical_range_accuracy: str = Field(..., min_length=1, max_length=1200)

class CriterionScoreBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_response: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)
    coherence_cohesion: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)
    lexical_resource: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)
    grammatical_range_accuracy: float = Field(..., ge=0.0, le=9.0, multiple_of=0.5)

class AssessmentOutput(BaseModel):
    """Reasoning, feedback, and annotations precede criterion_scores."""
    model_config = ConfigDict(extra="forbid")
    criterion_feedback: CriterionFeedbackText
    sentence_annotations: list[SentenceAnnotation] = Field(max_length=10)
    top_weaknesses: list[WeaknessSummary] = Field(min_length=1, max_length=3)
    criterion_scores: CriterionScoreBlock
```

- **Server Post-Processing:** Reuses `reject_question_evidence()` and verbatim substring grounding (`validate_grade()`): strips any `original_sentence` not found verbatim in `essay_text` or leaked from `prompt_text`.

### 3.3. Offline Calibration Protocol (`80–100` Graded Teacher Essays)
Executed offline using our existing Python R&D suite (`src/data/splitter.py`, `src/eval/metrics.py`, `src/eval/loo_audit.py`, `src/eval/calibrate_v0.py`):
- **Cluster-Disjoint Partition (`cosine < 0.60`):** `Seed: 10–12` (anchors), `Dev: 38–48` (prompt tuning & offset fitting), `Holdout: 30–40` (one-shot final blind evaluation), with **Tail Protection** on `<= 5.0` and `>= 8.0`.
- **Intra-Rater Outlier Audit:** Flag and inspect any teacher essay where `criterion_spread > 2.0` or where `overall` differs from IELTS `ROUND_HALF_UP` by `> 0.5`.
- **Acceptance Gates:** `QWK >= 0.70`, `|SMD| <= 0.15`, `SD Ratio in [0.67, 1.50]`, `Macro-MAE <= 0.40` (verified via 1,000 Clustered Bootstrap resamples).

---

## 4. Module 2 — Format-Locked Personalized Practice Generator

### 4.1. Decoupled Stage 2 Call
Triggered automatically by the `asyncio` worker immediately after Stage 1 saves `assessments` (never merged into Stage 1, preserving scoring accuracy and prompt cache prefix stability).

### 4.2. Format Locking & Auto-Grading
- **Prompt Inputs:** Stage 1 `top_weaknesses` + verified `sentence_annotations` + **3–5 active `exercise_templates` per format** authored by Teacher Nguyên.
- **Structured Output (`PracticeSetOutput`):** Enforces 3–5 exercises across:
  1. `INFORMAL_TO_FORMAL`: `{ instruction, informal_sentence, weak_phrases, model_rewrite, accepted_alternatives, explanation }`
  2. `TARGETED_ERROR_CORRECTION`: `{ instruction, flawed_sentence, error_span, corrected_sentence, accepted_alternatives, hint, explanation }`
  3. `GUIDED_FILL_IN_BLANKS`: `{ instruction, sentence_with_blanks, word_bank, answers[], explanation }`
- **Deterministic Backend Auto-Grading (`$0` cost):**
  - `GUIDED_FILL_IN_BLANKS`: Case-insensitive trimmed exact match per blank index against `answers[]`.
  - `INFORMAL_TO_FORMAL` & `TARGETED_ERROR_CORRECTION`: Normalized text match (`casefold`, collapsed whitespace/punctuation) against `model_rewrite` / `corrected_sentence` / `accepted_alternatives`, falling back to token-level Jaccard/Levenshtein similarity (`>= 0.88`) or optional lightweight micro-check if ambiguous.

---

## 5. REST API Contract (FastAPI)

| Group | Method & Path | Auth / Role | Request / Response Summary |
|---|---|---|---|
| **Health** | `GET /api/health` | Public | `{ status: "ok", queue_depth, worker_active }` |
| **Auth / Class** | `POST /api/auth/join-class` | `student+` | `{ join_code }` → enrolls in `YP03`/`YP04`/`YP05` |
| **Auth Handoff** | `POST /api/auth/portal-handoff` | Public (HMAC JWT) | Exchanges signed YP Portal token for Supabase/app session |
| **Prompts** | `GET /api/prompts` | `student+` | Lists published `CURATED_BANK` prompts (+ topic filters) |
| **Prompts Admin** | `POST /api/prompts`, `PATCH /api/prompts/{id}` | `teacher` \| `admin` | Create/publish/unpublish curated prompts |
| **Submit Essay** | `POST /api/submissions` | `student+` | `{ prompt_id? \| custom_prompt_text?, essay_text }` → `202 { submission_id, status: "QUEUED", queue_position }` |
| **Poll Status** | `GET /api/submissions/{id}/status` | Owner \| `ta+` | `{ status, queue_position?, error_message? }` |
| **Get Result** | `GET /api/submissions/{id}` | Owner \| `ta+` | Full submission + `assessment` (`overall ± 0.5`, 4 scores, feedback, sentence annotations) + `practice_set` |
| **History** | `GET /api/submissions` | `student+` | Paginated history & longitudinal score series for current student |
| **Practice** | `POST /api/practice/{set_id}/submit` | Owner | `{ answers: [...] }` → auto-graded `score_summary_json` & feedback |
| **Teacher Review** | `GET /api/teacher/classes/{class_id}/submissions` | `ta` \| `teacher` \| `admin` | Class-wide submission list & filter by student/prompt/status |
| **Teacher Override** | `PATCH /api/teacher/assessments/{id}/override` | `teacher` \| `admin` | Saves `teacher_override_json` & `reviewed_by` alongside AI output |
| **Calibration & Templates** | `CRUD /api/admin/anchors`, `/api/admin/templates` | `teacher` \| `admin` | Manage `teacher_anchors` & `exercise_templates` |
| **Usage Metrics** | `GET /api/admin/metrics` | `admin` | Daily submissions, token usage, mean latency, failure rate |

---

## 6. Frontend UX & Role-Based Views (React + Tailwind)

- **Student Workspace:**
  - **Prompt Selector & Editor:** Switch between *Assigned / Curated Bank* and *Custom Prompt*, live word counter (`250+ words` target indicator), revision button (*"Revise & Resubmit"* linking `attempt_number + 1` to the same `prompt_id`).
  - **Queue Status Banner:** Live queue position & estimated wait during end-of-class bursts.
  - **Split-Screen Assessment Viewer:** Left pane displays essay with clickable color-coded sentence highlights (`grammar_syntax`, `lexical_collocation`, `coherence_cohesion`, `task_response`); right pane shows **`Overall ± 0.5 / 9`**, 4 criterion cards, Teacher Nguyên-voiced feedback, `minimal_fix` vs `band_upgrade` diffs, and disclaimer.
  - **Interactive Practice Tab:** Step-by-step drills locked to Nguyên's templates with instant `$0` feedback & hints.
  - **Progress Dashboard:** Longitudinal line chart of `Overall`, `TR`, `CC`, `LR`, `GRA` across attempts.
- **Teacher / TA Workspace:**
  - Class filter (`YP03`, `YP04`, `YP05`), student submission table, side-by-side AI grade + Teacher Override/Endorse panel, Question Bank & Exercise Template editor, and Anchor manager.

---

## 7. Guardrails, Security & Anti-Abuse Controls

1. **`$0` Pre-LLM Input Gates:**
   - **Word Count:** Reject `< 50` or `> 1,200` words (`422`); flag `50–249` words for IELTS under-length `TR` scrutiny.
   - **Gibberish / Repetition:** Reject scripts with unique-token ratio `< 0.25` or alphabetic ratio `< 0.60`.
   - **Prompt-Copy Overlap:** 5-gram Jaccard / sentence match against prompt; if `> 50%` copied from prompt, block (`422`) or strip copied lines before scoring.
2. **Prompt Injection Defense:** Wrap `<task_prompt>` and `<student_essay>` in strict XML delimiters, harden `system_instruction`, enforce Pydantic clamping `[0.0, 9.0]` in `0.5` steps, and compute `overall_score` strictly server-side.
3. **Access & Cost Protection:** Class `join_code` gating during onboarding, per-student daily cap (`3` submissions/day) + `2-minute` cooldown, backend-only `GEMINI_API_KEY`, and strict **PII stripping** (never transmit student name/email to Gemini).

---

## 8. Deployment Architecture, Roadmap & Cost Analysis

### 8.1. Deployment Topology & Monthly Cost (~100 Active Students)

| Layer | Hosting Choice | Pilot Cost | Production Recommended |
|---|---|---:|---:|
| **Frontend SPA** | Cloudflare Pages or Vercel Static | `$0/mo` | `$0/mo` |
| **FastAPI + Worker (`Dockerfile`)** | Render / Koyeb Free Tier (Pilot) → `$5/mo` 2GB VPS (Hetzner/DigitalOcean/Railway) | `$0/mo` | **`$5/mo`** *(zero cold-start, handles 40-student bursts reliably)* |
| **PostgreSQL + Auth** | Supabase Free Tier (`500 MB`, `50k MAUs`) | `$0/mo` | `$0/mo` |
| **Gemini API (`Flash-Lite` / `Flash`)** | Google AI Studio | `$0` *(Free Tier, pilot < 200 req/day)* | **`~$1.50 – $3.00/mo`** *(Paid Tier `Flash-Lite` w/ Implicit Cache for ~800–2,000 essays/mo; zero training on student data)* |

### 8.2. 3-Phase Implementation Roadmap & Client Intake Checklist

- **Client Data Intake Needed:**
  1. **80–100 graded essays** from Teacher Nguyên (`Seed: 10–12`, `Dev: 38–48`, `Holdout: 30–40`) with 4 criterion scores (`TR/CC/LR/GRA`) + written feedback across Bands `4.5–8.5+`.
  2. **3–5 sample exercises per format** authored by Teacher Nguyên (*Informal-to-Formal*, *Targeted Error Correction*, *Guided Fill-in-the-Blanks*).
  3. *(Optional)* Export of Nguyên's existing IELTS Custom GPT instructions to accelerate Style Profile authoring.
- **Phase 1 (~5–7 days):** Supabase schema + Alembic migrations, FastAPI Auth/Class/Prompt CRUD, `$0` input gates, `asyncio` + `SKIP LOCKED` queue, Stage 1 porting (`V1_STRATIFIED` fallback anchors) + React Student Workspace.
- **Phase 2 (~4–5 days):** Stage 2 decoupled Practice Generator, `exercise_templates` seeding, interactive drill UI + `$0` auto-grader, longitudinal progress chart, and Teacher/TA override view.
- **Phase 3 (~4–6 days):** Offline calibration (`splitter.py`, `loo_audit.py`, `metrics.py`, `calibrate_v0.py`) on Nguyên's 80–100 graded essays (`QWK >= 0.70`, `|SMD| <= 0.15`), swap `teacher_anchors` into production, and deploy to `$5/mo` VPS + Cloudflare Pages.
