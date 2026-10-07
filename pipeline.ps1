# Rebuild everything from the public sources:
#   download -> clean & match -> ledger -> train -> evaluate
# Usage:  powershell -ExecutionPolicy Bypass -File pipeline.ps1 [-SkipDownload] [-Quick]
#   -SkipDownload  reuse data\raw (the Comtrade download takes a while because of its quota)
#   -Quick         one seed and fewer epochs, for a fast check

param([switch]$SkipDownload, [switch]$Quick)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$env:TEMP = "$Root\.cache\tmp"; $env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
$env:PYTHONPATH = "$Root\backend"
$env:PYTHONUNBUFFERED = "1"
$py = "$Root\.venv\Scripts\python.exe"
Set-Location "$Root\backend"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Run { & $py @args; if ($LASTEXITCODE -ne 0) { throw "failed: $args" } }

if (-not $SkipDownload) { Step "Downloading public data"; Run -m foodtrace.data.fetch }
Step "Cleaning and matching";      Run -m foodtrace.data.process
Step "Building the ledger";        Run -m foodtrace.ledger.store build
Step "Training models"
if ($Quick) { Run -m foodtrace.model.train --quick } else { Run -m foodtrace.model.train }
Step "Evaluating";                 Run -m foodtrace.model.evaluate
Write-Host "`nDone. Start the app with .\run.ps1" -ForegroundColor Green
