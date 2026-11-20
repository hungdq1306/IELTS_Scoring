@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\.cache\pilot-deps;%CD%\.cache\runtime-py;%CD%\backend"
set "FOGWRITE_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "FOGWRITE_PYTHON=%CD%\.venv\Scripts\python.exe"
"%FOGWRITE_PYTHON%" -m app.setup_clerk --check
if errorlevel 1 goto failed
echo.
echo FogWrite with Clerk: http://localhost:8000
echo Use localhost, not 127.0.0.1: the authorized origin must match.
echo Keep this window open. Press Ctrl+C to stop.
"%FOGWRITE_PYTHON%" -m uvicorn app.pilot:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
:failed
echo.
echo Server stopped. Run SETUP_CLERK.cmd first if configuration is missing.
pause
