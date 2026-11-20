@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\.cache\pilot-deps;%CD%\.cache\runtime-py;%CD%\backend"
set "FOGWRITE_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "FOGWRITE_PYTHON=%CD%\.venv\Scripts\python.exe"
echo Configure Clerk DEVELOPMENT for FogWrite on http://localhost:8000
echo First create FogWrite in https://dashboard.clerk.com/ and enable Email and Google.
echo Copy its Publishable Key pk_test_... . Do not use an sk_ secret key.
echo.
"%FOGWRITE_PYTHON%" -m app.setup_clerk
if errorlevel 1 goto failed
"%FOGWRITE_PYTHON%" -m alembic -c backend/alembic.ini upgrade head
if errorlevel 1 goto failed
"%FOGWRITE_PYTHON%" -m app.manage seed
if errorlevel 1 goto failed
echo.
echo Setup complete. Open RUN_FOGWRITE_CLERK.cmd to start the authenticated MVP.
pause
exit /b 0
:failed
echo.
echo Setup stopped. If a dependency is missing, install backend/requirements-dev.txt.
echo No claim is made that Clerk sign-in or database setup succeeded.
pause
exit /b 1
