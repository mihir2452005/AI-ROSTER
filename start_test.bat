@echo off
set RATE_LIMIT_REQUESTS=10000
set RATE_LIMIT_WINDOW=1
set ADMIN_API_KEY=dev-secret-change-in-prod
backend\.venv\Scripts\python.exe run.py --backend-only