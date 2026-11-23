@echo off
setlocal
cd /d "%~dp0"
echo FogWrite offline demo - open http://127.0.0.1:8000/guide
echo Try the guide, sample assessment, topics, countdown timer and saved drafts.
echo Real AI grading and classroom accounts require their respective backend.
node scripts/preview-guide.cjs
pause
