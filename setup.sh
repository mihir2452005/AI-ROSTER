#!/usr/bin/env bash
# RoastGPT — one-time setup. Run this after cloning the repo.
# Usage:  bash setup.sh

set -euo pipefail
cd "$(dirname "$0")"

step() { printf "\n\033[1;36m===> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m[OK]\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m[FAIL]\033[0m %s\n" "$1"; exit 1; }

# 1. Python
step "Checking Python (3.10+)"
if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not on PATH. Install from https://python.org"
fi
PY=python3
PYVER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PYMAJOR" -lt 3 ] || [ "$PYMINOR" -lt 10 ]; then
    fail "Python 3.10+ required (found $PYVER)"
fi
ok "Python $PYVER"

# 2. Node
step "Checking Node (18+)"
if ! command -v node >/dev/null 2>&1; then
    fail "node not on PATH. Install from https://nodejs.org"
fi
NODEVER=$(node --version | sed 's/v//')
NODEMAJOR=$(echo "$NODEVER" | cut -d. -f1)
if [ "$NODEMAJOR" -lt 18 ]; then
    fail "Node 18+ required (found $NODEVER)"
fi
ok "Node $NODEVER"

# 3. Backend venv
step "Backend venv + deps"
if [ ! -d "backend/.venv" ]; then
    $PY -m venv backend/.venv
    ok "Created backend/.venv"
else
    ok "backend/.venv already exists"
fi
backend/.venv/bin/pip install --upgrade pip --quiet
backend/.venv/bin/pip install -r backend/requirements.txt --quiet
ok "Backend deps installed"

# 4. Frontend deps
step "Frontend deps"
if [ ! -d "frontend/node_modules" ]; then
    (cd frontend && npm install)
    ok "Installed frontend/node_modules"
else
    ok "frontend/node_modules already exists"
fi

printf "\n\033[1;32m===> Setup complete.\033[0m\n"
printf "    Run:  python run.py\n"
