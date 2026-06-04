# RoastGPT — one-time setup. Run this after cloning the repo.
# Usage:  .\setup.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step($msg)  { Write-Host "`n===> $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "  [FAIL] $msg" -ForegroundColor Red; exit 1 }

# 1. Python
Step "Checking Python (3.10+)"
$py = $null
if (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
elseif (Get-Command py -ErrorAction SilentlyContinue)   { $py = "py -3" }
else { Fail "Python not on PATH. Install from https://python.org" }
$ver = & $py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([int]$ver.Split('.')[0] -lt 3 -or [int]$ver.Split('.')[1] -lt 10) {
    Fail "Python 3.10+ required (found $ver)"
}
Ok "Python $ver"

# 2. Node
Step "Checking Node (18+)"
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { Fail "Node not on PATH. Install from https://nodejs.org" }
$nodeVer = (& node --version) -replace 'v',''
[int]$major = [int]($nodeVer.Split('.')[0])
if ($major -lt 18) { Fail "Node 18+ required (found $nodeVer)" }
Ok "Node $nodeVer"

# 3. Backend venv
Step "Backend venv + deps"
$venv = "backend\.venv"
if (-not (Test-Path $venv)) {
    & $py -m venv $venv
    Ok "Created $venv"
} else {
    Ok "$venv already exists"
}
& "$venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$venv\Scripts\python.exe" -m pip install -r backend\requirements.txt --quiet
Ok "Backend deps installed"

# 4. Frontend deps
Step "Frontend deps"
if (-not (Test-Path "frontend\node_modules")) {
    Push-Location frontend
    npm install
    Pop-Location
    Ok "Installed frontend/node_modules"
} else {
    Ok "frontend/node_modules already exists"
}

# 5. Sanity check
Step "Sanity check"
$health = $null
try {
    $body = (Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 2).Content
    if ($body -match '"status":"ok"') { $health = "already running" }
} catch { }
if ($health) {
    Ok "Backend already running: $body"
} else {
    Ok "Backend not running yet (that's fine — `python run.py` will start it)"
}

Write-Host ""
Write-Host "===> Setup complete." -ForegroundColor Green
Write-Host "    Run:  python run.py" -ForegroundColor Cyan
Write-Host "    Or :  .\run.bat" -ForegroundColor Cyan
Write-Host "    Or :  .\run.ps1" -ForegroundColor Cyan
