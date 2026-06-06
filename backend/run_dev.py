#!/usr/bin/env python
"""Start the dev server in the background. Used by smoke_test.py."""
import os
import subprocess
import sys
import time

os.environ.update({
    "ENVIRONMENT": "test",
    "ALLOW_INSECURE_DEFAULTS": "1",
    "ADMIN_API_KEY": "test-admin-key-1234567890",
    "JWT_SECRET_KEY": "test-secret-key-32-bytes-minimum-1234",
    "RATE_LIMIT_REQUESTS": "10000",
    "RATE_LIMIT_WINDOW": "1",
    "RATE_LIMIT_REGISTER": "10000",
    "RATE_LIMIT_LOGIN": "10000",
    "RATE_LIMIT_REFRESH": "10000",
    "RATE_LIMIT_SESSION_START": "10000",
    "RATE_LIMIT_CONTACT": "10000",
    "RATE_LIMIT_ADMIN_CLEANUP": "10000",
    "DISABLE_BACKGROUND_JOBS": "1",
    "LLM_PROVIDER": "stub",
    "SQLITE_FILE": "smoke.db",
    "PYTHONIOENCODING": "utf-8",
})

# Clean any stale files.
for f in ("smoke.db", "dev_emails.log", "server_err.log", "server_out.log"):
    try:
        os.unlink(f)
    except FileNotFoundError:
        pass

# Spawn.
log = open("server_out.log", "w", encoding="utf-8")
err = open("server_err.log", "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--port", "8765", "--log-level", "warning"],
    env=os.environ, stdout=log, stderr=err,
)
print(f"started pid={proc.pid}")
time.sleep(4)
print(open("server_out.log", encoding="utf-8").read()[-2000:])
print(open("server_err.log", encoding="utf-8").read()[-2000:])
