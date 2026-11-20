$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
Write-Host 'FogWrite: http://127.0.0.1:8000'
Write-Host 'Keep this terminal open. Press Ctrl+C to stop.'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
