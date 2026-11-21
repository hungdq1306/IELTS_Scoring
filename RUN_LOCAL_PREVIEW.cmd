@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\backend"
set "APP_ENV=development"
set "DATABASE_URL=sqlite+aiosqlite:///./results/local-preview.sqlite3"
set "FRONTEND_ORIGIN=http://localhost:8000"
set "WORKER_ENABLED=false"
set "FOGWRITE_NODE_MODULES=%CD%\.cache\pilot-ui-deps\node_modules"
node scripts/build-frontend.cjs
if errorlevel 1 exit /b 1
if not exist results mkdir results
".venv\Scripts\python.exe" -c "from sqlalchemy import create_engine; from app.models import Base; e=create_engine('sqlite:///./results/local-preview.sqlite3'); Base.metadata.create_all(e); e.dispose()"
if errorlevel 1 exit /b 1
echo Open http://localhost:8000 and sign in with Clerk.
echo Separate local database. AI workers disabled for UI preview.
".venv\Scripts\python.exe" -m uvicorn app.pilot:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
pause
