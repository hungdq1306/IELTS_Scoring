@echo off
setlocal
cd /d "%~dp0..\.."
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" -m benchmarks.task1_extraction.prepare_essayjudge %*
if errorlevel 1 exit /b 1
"%PYTHON%" -m benchmarks.task1_extraction.run_benchmark %*
if errorlevel 1 exit /b 1
"%PYTHON%" -m benchmarks.task1_extraction.audit_consistency %*
exit /b %errorlevel%
