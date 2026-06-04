@echo off
REM RoastGPT — run backend + frontend in one terminal.
REM Just double-click or run:  run.bat

setlocal
cd /d "%~dp0"

REM Use the system Python (works whether venv is activated or not)
where python >nul 2>nul
if errorlevel 1 (
    echo [run.bat] python not on PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)

python run.py %*
endlocal
