# RoastGPT — run backend + frontend in one terminal.
# Usage:  .\run.ps1            # dev mode (live reload)
#         .\run.ps1 -Prod      # production build
#         .\run.ps1 -Build     # build first, then dev
#         .\run.ps1 -BackendOnly

param(
    [switch]$Prod,
    [switch]$Build,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoColor
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = $null
if (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
elseif (Get-Command py -ErrorAction SilentlyContinue) { $py = "py" }
else {
    Write-Host "[run.ps1] python not on PATH. Install Python 3.10+ first." -ForegroundColor Red
    exit 1
}

$args = @()
if ($Prod)        { $args += "--prod" }
if ($Build)       { $args += "--build" }
if ($BackendOnly) { $args += "--backend-only" }
if ($FrontendOnly){ $args += "--frontend-only" }
if ($NoColor)     { $args += "--no-color" }

& $py run.py @args
