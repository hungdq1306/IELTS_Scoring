> Historical snapshot. This document records an earlier implementation or proposal. For current behavior, see [documentation](../README.md) and [architecture](../ARCHITECTURE.md).

# Personalized practice demo

## Start

From PowerShell in the repository root, with the existing Python environment activated and Gemini credentials in the existing backend environment:

```powershell
$env:PYTHONPATH = 'backend'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 when frontend/dist exists (the backend serves the built application). For frontend development in a second terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Keep the existing Vite backend proxy configuration. Production build: npm run build inside frontend. Do not put Gemini credentials in frontend variables.

## Live walkthrough

1. Submit an IELTS Task 2 question and an essay with real mistakes through the existing grading form. Confirm original feedback and scores remain visible.
2. Select Practice Your Mistakes, then Generate Practice. Show the elapsed/loading state. No call starts merely by viewing the grading result.
3. Expand source evidence. Explain that exact evidence is checked and semantic judgments remain automated.
4. Answer a recognition exercise, then use Next Exercise for correction/transfer. Check Answer reveals the key only after submission. Try Show Hint and inspect the persisted hint count.
5. Open Revision & Progress, select a paragraph with an approved weakness, revise it and submit. Inspect target-specific feedback and before/after text; there is no new IELTS band.
6. Reload and select the saved assessment. Exercises, feedback, hints and revisions should remain available in the same browser session. Return to Writing Feedback.
7. If fewer exercises survive validation, show that result honestly. Do not manufacture mistakes or promise every essay has all exercise types.

## Verification and independent benchmark

```powershell
$env:PYTHONPATH = 'backend'
python -m pytest backend/tests -m 'not live'
python -m benchmark.practice --max-samples 20 --request-budget 55 --daily-budget 300
python -m benchmark.practice --export-only
```

Benchmark resumes a frozen manifest and skips ready batches, so rerunning does not rebill them. Failed operations are retried only with --retry-failures and remain bounded by two generations per submission. Avoid running the benchmark and demo concurrently when quota is tight. Existing provider quota settings, actual Google limits and network availability still apply.

Lecturer exports live in results/practice_benchmark/lecturer_errors.csv and lecturer_exercises.csv. Enter 1/0 or leave each human criterion blank. Re-export preserves entered judgments. Do not share the private database, source essays or review answer keys through public learner endpoints.

## Verified running demo

The updated application is currently running at http://127.0.0.1:8002/. The verification browser contains a saved technology/education assessment with three exercises, two completed answers, one hint and a saved revised paragraph. Restore it using the saved-assessment dropdown in the same browser. This demo essay is deliberately short and contains agreement mistakes; its predicted band is not a validated score. The normal start command above uses port 8000; use --port 8002 to reproduce this port after stopping the existing demo process.
