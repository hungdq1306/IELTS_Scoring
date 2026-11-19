# Live Demo Guide

## 1. Starting the Application

Ensure `GEMINI_API_KEY` is configured in `.env`, then start FastAPI from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in your browser (press `Ctrl+F5` if reloading over a cached build).

## 2. Grading an Essay

1. Choose **Assessment method**:
   - **`Calibrated v1 · 8 Examiner Anchors (5.0-9.0)`** (`V1_STRATIFIED`, **default**): Uses Prompt `v1` + 8 stratified examiner-verified anchors covering Bands 5.0–9.0.
   - **`Rubric v1 Only`** (`FS0`): Zero-shot May 2023 calibrated rubric without few-shot anchors.
   - **`Lecturer · 5-Shot (5.0-8.0)`** (`FS5_FULL`): Legacy 5-essay lecturer reference set.
2. Paste an IELTS Writing Task 2 prompt and essay (use blank lines between paragraphs), or click **Load sample**.
3. Click **Evaluate essay**.
4. Review the **Estimated Task 2 band**, four criterion scores (`TR`, `CC`, `LR`, `GRA`), 16 writing diagnostics, verbatim grounded evidence, grammar corrections, optional language suggestions, and paragraph-by-paragraph feedback.

> **Note on Reference Overlap Protection:** Pasting an essay or prompt that is already part of the 8 `V1_STRATIFIED` calibration anchors intentionally returns HTTP `409` (`reference_overlap`) to prevent self-grading reference contamination. Select `FS0` to evaluate those prompts directly.

## 3. Personalized Practice & Revision

After receiving an assessment, open the **Practice Your Mistakes** section below the score breakdown to generate targeted exercises from your weakest areas, request hints, submit revisions, or restore prior assessments from the current browser session.
