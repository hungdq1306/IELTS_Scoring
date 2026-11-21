# Demo and classroom acceptance

## Local demo

Use `RUN_FOGWRITE.cmd` or run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` with `PYTHONPATH=backend`. This uses cookie-owned local history and research assessment options. Configure Gemini server-side in `.env`.

## Authenticated pilot

Use `SETUP_CLERK.cmd` then `RUN_FOGWRITE_CLERK.cmd` for development. For Render/Neon and live Clerk configuration follow [deployment](../backend/README_DEPLOY.md); production runs `app.pilot:app`.

1. Sign in and explicitly accept participation/privacy conditions.
2. As teacher/admin, create a class and copy an invitation. As student, join it and select the class.
3. Choose Writing Practice for a timed prompt or Check My Essay to paste a question and essay. Confirm the submitting-to class and submit once.
4. Review criterion bands, essay evidence and sentence feedback. Generate personalized exercises, answer the entire set and submit it for coaching.
5. Reopen the assessment from History. Reload a timed draft and verify mode/countdown restoration.
6. Switch between two test accounts, including while restoration is pending; confirm no previous account essay/history/draft appears.
7. Verify TA access is read-only and limited to assigned classes; verify student requests cannot access admin resources.
8. In admin, inspect usage, failures and audit; test quota updates and failed-job retry with explicit test data.

Use authorized test accounts and a staging database for acceptance. Real Gemini calls consume quota. A successful request verifies integration, not scoring accuracy. Historical demo records are in [archive](archive/README.md).
