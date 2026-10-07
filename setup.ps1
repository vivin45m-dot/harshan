# One-time setup. Everything is installed inside this folder:
#   .tools\uv       package manager
#   .tools\python   Python 3.12
#   .venv           Python packages
#   .cache          download caches and temp files
#   frontend\node_modules
# Nothing is written to C:, so it also works on machines with a full system drive.
#
# Needs: internet access, and Node.js 20+ for the dashboard (https://nodejs.org).
# Usage:  powershell -ExecutionPolicy Bypass -File setup.ps1 [-Cpu]

param([switch]$Cpu)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

# Keep every cache and temp file inside the project.
$env:TEMP = "$Root\.cache\tmp"; $env:TMP = $env:TEMP
$env:UV_CACHE_DIR = "$Root\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$Root\.tools\python"
$env:UV_PYTHON_BIN_DIR = "$Root\.tools\python\bin"
$env:UV_LINK_MODE = "copy"
$env:npm_config_cache = "$Root\.cache\npm"
New-Item -ItemType Directory -Force $env:TEMP, "$Root\.tools" | Out-Null

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

$uv = "$Root\.tools\uv\uv.exe"
if (-not (Test-Path $uv)) {
    Step "Downloading uv"
    $zip = "$env:TEMP\uv.zip"
    Invoke-WebRequest "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip
    Expand-Archive $zip "$Root\.tools\uv" -Force
}

Step "Python 3.12 and virtual environment"
& $uv python install 3.12
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) { & $uv venv "$Root\.venv" --python 3.12 }
$py = "$Root\.venv\Scripts\python.exe"

$hasGpu = $false
if (-not $Cpu) {
    try { nvidia-smi -L | Out-Null; $hasGpu = ($LASTEXITCODE -eq 0) } catch { $hasGpu = $false }
}
if ($hasGpu) {
    Step "PyTorch (CUDA build, NVIDIA GPU found)"
    & $uv pip install --python $py torch==2.14.1 --index-url https://download.pytorch.org/whl/cu126
} else {
    Step "PyTorch (CPU build)"
    & $uv pip install --python $py torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
}

Step "Python packages"
& $uv pip install --python $py -r "$Root\requirements.txt"

Step "Dashboard (npm install + build)"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Warning "Node.js not found - install it from https://nodejs.org and run setup again for the dashboard."
} else {
    Push-Location "$Root\frontend"
    npm ci
    npm run build
    Pop-Location
}

Step "Checking"
& $py -c "import torch, fastapi, pandas; print('torch', torch.__version__, '| cuda' if torch.cuda.is_available() else '| cpu')"
Write-Host "`nSetup finished. Start the app with:  .\run.ps1" -ForegroundColor Green
