@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\.cache\runtime-py;%CD%\backend"
echo FogWrite local MVP
echo Open http://127.0.0.1:8000 after Application startup complete.
echo Essay grading: Gemini 3.5 Flash-Lite
echo Complete-set practice feedback: Gemini 3.1 Flash-Lite
echo Keep this window open. Press Ctrl+C to stop.
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
) else (
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
)
echo.
echo The server has stopped. If a dependency is missing, install requirements.txt first.
pause
