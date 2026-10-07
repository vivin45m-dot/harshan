# Start the API and dashboard on http://127.0.0.1:8000
# Usage:  powershell -ExecutionPolicy Bypass -File run.ps1 [-Port 8000] [-Dev]
#   -Dev  also starts the Vite dev server on :5173 with hot reload

param([int]$Port = 8000, [switch]$Dev)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$env:TEMP = "$Root\.cache\tmp"; $env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
$env:PYTHONPATH = "$Root\backend"
$py = "$Root\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) { throw "Run setup.ps1 first." }
if (-not (Test-Path "$Root\artifacts\evidential.pt")) { throw "No trained model in artifacts\ - run pipeline.ps1 first." }
if (-not (Test-Path "$Root\data\ledger.sqlite3")) {
    Write-Host "Building the provenance ledger (first run only, about a minute)..."
    & $py -m foodtrace.ledger.store build
}

if ($Dev) {
    Start-Process -WorkingDirectory "$Root\frontend" -FilePath "npm" -ArgumentList "run", "dev"
    Start-Process "http://localhost:5173"
} else {
    if (-not (Test-Path "$Root\frontend\dist\index.html")) { throw "Dashboard not built - run setup.ps1 (needs Node.js)." }
    Start-Process "http://127.0.0.1:$Port"
}
& $py -m uvicorn foodtrace.api.main:app --host 127.0.0.1 --port $Port --app-dir "$Root\backend"
