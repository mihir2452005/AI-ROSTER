# RoastGPT — convenience targets.
# Use `make <target>` (Unix, or with make installed on Windows).

.PHONY: help run run-prod run-backend run-frontend build test setup clean

help:
	@echo "RoastGPT make targets:"
	@echo "  make setup        - first-time setup (venv, npm install)"
	@echo "  make run          - run backend + frontend (next dev)"
	@echo "  make run-prod     - run with built frontend (next start)"
	@echo "  make run-backend  - only the API on :8000"
	@echo "  make build        - build the frontend for production"
	@echo "  make test         - run backend tests"
	@echo "  make clean        - stop servers + clear build artifacts"

run:
	python run.py

run-prod:
	python run.py --prod

run-backend:
	python run.py --backend-only

run-frontend:
	python run.py --frontend-only

build:
	python run.py --build

test:
	cd backend && .venv/Scripts/python.exe -m pytest tests/ -v

setup:
ifeq ($(OS),Windows_NT)
	powershell -ExecutionPolicy Bypass -File setup.ps1
else
	bash setup.sh
endif

clean:
	@echo "Stopping any lingering servers on :3000/:8000..."
	-@taskkill /F /IM uvicorn.exe 2>nul
	-@taskkill /F /IM node.exe /FI "WINDOWTITLE eq next*" 2>nul
	-@rm -rf frontend/.next
	-@rm -rf frontend/node_modules/.cache
