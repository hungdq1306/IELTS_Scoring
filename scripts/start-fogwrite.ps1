param([ValidateRange(1,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
$practiceRuntime = Join-Path $projectRoot '.cache/runtime-py'
if (Test-Path -LiteralPath $practiceRuntime) {
    $env:PYTHONPATH = "$practiceRuntime;$env:PYTHONPATH"
}
Write-Host "FogWrite: http://127.0.0.1:$Port"
Write-Host 'Local MVP: browser-session history; Clerk classroom pilot is configured separately.'
Write-Host 'Essay: Gemini 3.5 Flash-Lite. Complete-set practice feedback: Gemini 3.1 Flash-Lite.'
Write-Host 'Keep this terminal open. Press Ctrl+C to stop.'
$venvPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
} else {
    python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
}
