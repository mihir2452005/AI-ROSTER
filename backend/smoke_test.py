"""End-to-end smoke test against a running backend on port 8765.

Hits every public endpoint, every Round 9 surface, and the health/metrics
endpoints. Stops with a non-zero exit on any failure.

Run:
    ENVIRONMENT=test ALLOW_INSECURE_DEFAULTS=1 \\
    ADMIN_API_KEY=test-admin-key-1234567890 \\
    JWT_SECRET_KEY=test-secret-key-32-bytes-minimum-1234 \\
    DISABLE_BACKGROUND_JOBS=1 LLM_PROVIDER=stub SQLITE_FILE=smoke.db \\
    python smoke_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, Tuple

import httpx

# Force UTF-8 stdout on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8765"
ADMIN_KEY = "test-admin-key-1234567890"


def _check(name: str, ok: bool, detail: str = "") -> bool:
    flag = "OK " if ok else "FAIL"
    print(f"  [{flag}] {name}{(' — ' + detail) if detail else ''}")
    return ok


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    failures = 0
    with httpx.Client(timeout=20.0) as c:
        # 1. Health (public)
        section("Health")
        try:
            r = c.get(f"{BASE}/api/health")
            failures += not _check("GET /api/health", r.status_code == 200, str(r.json())[:120])
        except Exception as e:
            failures += not _check("GET /api/health", False, str(e))
            print("\nServer unreachable — aborting.")
            return 1

        # 2. Public status
        section("Round 9 — public system status")
        for path in ("/api/v1/system/status", "/api/system/status"):
            r = c.get(f"{BASE}{path}")
            failures += not _check(f"GET {path}", r.status_code == 200, str(r.json())[:120])

        # 3. Public Prometheus metrics
        section("Round 9 — Prometheus metrics")
        for path in ("/api/v1/system/metrics", "/api/metrics", "/api/v1/metrics"):
            r = c.get(f"{BASE}{path}")
            ok = r.status_code == 200 and "roastgpt_build_info" in r.text
            failures += not _check(f"GET {path}", ok, r.text[:120].replace("\n", " "))

        # 4. Register + login
        section("Auth — register + login")
        email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
        password = "smokepass1234"
        r = c.post(f"{BASE}/api/v1/auth/register", json={
            "email": email, "password": password, "full_name": "Smoke Test",
        })
        if r.status_code != 200 and r.status_code != 201:
            failures += not _check("POST /auth/register", False, str(r.json())[:200])
            print("Aborting — register failed.")
            return 1
        _check("POST /auth/register", True, f"status={r.status_code}")
        tokens = r.json()
        access = tokens.get("access_token") or tokens.get("access")
        refresh = tokens.get("refresh_token") or tokens.get("refresh")
        auth = {"Authorization": f"Bearer {access}"}

        # 5. /me
        r = c.get(f"{BASE}/api/v1/auth/me", headers=auth)
        failures += not _check("GET /auth/me", r.status_code == 200, str(r.json())[:120])

        # 6. Activity feed (Round 9)
        r = c.get(f"{BASE}/api/v1/auth/me/activity", headers=auth)
        failures += not _check("GET /auth/me/activity", r.status_code == 200, str(r.json())[:120])

        # 7. Notifications list (Round 9)
        r = c.get(f"{BASE}/api/v1/notifications", headers=auth)
        failures += not _check("GET /notifications", r.status_code == 200, str(r.json())[:120])

        # 8. Public contact form
        r = c.post(f"{BASE}/api/v1/contact", json={
            "name": "Smoke Tester", "email": "smoke@example.com",
            "subject": "Hello there", "message": "Just a smoke test message.",
        })
        failures += not _check("POST /contact", r.status_code in (200, 201), str(r.json())[:200])

        # 9. Bootstrap an admin via the bootstrap script, then login.
        # We use the same SQLite the server is using.
        section("Admin")
        admin_email = f"smoke-admin-{uuid.uuid4().hex[:8]}@example.com"
        admin_password = "smokeadmin1234"
        try:
            import subprocess
            env = {**os.environ}
            env["ADMIN_EMAIL"] = admin_email
            env["ADMIN_PASSWORD"] = admin_password
            # Make sure the bootstrap points at the same DB the server
            # is using. The dev server reads SQLITE_FILE; if it's not
            # set it falls back to roastgpt_dev.db, which is NOT what
            # the smoke server uses. Mirror the variable explicitly.
            env.setdefault("SQLITE_FILE", "smoke.db")
            env.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-minimum-1234")
            env.setdefault("PYTHONIOENCODING", "utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "scripts.bootstrap_admin"],
                env=env, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                failures += not _check(
                    "bootstrap admin", False,
                    f"rc={result.returncode} stderr={result.stderr[:200]} stdout={result.stdout[:200]}",
                )
        except Exception as e:
            failures += not _check("bootstrap admin", False, str(e)[:200])
        else:
            # Login as admin
            r = c.post(f"{BASE}/api/v1/auth/login", json={
                "email": admin_email, "password": admin_password,
            })
            if r.status_code != 200:
                failures += not _check("POST /auth/login (admin)", False, str(r.json())[:200])
            else:
                admin_tokens = r.json()
                admin_access = admin_tokens.get("access_token") or admin_tokens.get("access")
                admin_auth = {"Authorization": f"Bearer {admin_access}"}

                r = c.get(f"{BASE}/api/v1/admin/stats", headers=admin_auth)
                failures += not _check("GET /admin/stats", r.status_code == 200, str(r.json())[:200])

                r = c.get(f"{BASE}/api/v1/admin/contact-messages", headers=admin_auth)
                failures += not _check("GET /admin/contact-messages", r.status_code == 200, str(r.json())[:200])

                r = c.post(f"{BASE}/api/v1/admin/notifications/broadcast", json={
                    "title": "Smoke test broadcast", "body": "Hello everyone",
                    "kind": "announcement", "target": "all",
                }, headers=admin_auth)
                failures += not _check("POST /admin/notifications/broadcast", r.status_code in (200, 201), str(r.json())[:200])

        # 12. Plans (public)
        r = c.get(f"{BASE}/api/v1/payments/plans")
        failures += not _check("GET /payments/plans", r.status_code == 200, str(r.json())[:200])

        # 13. Leaderboard (public)
        r = c.get(f"{BASE}/api/v1/leaderboard?period=week")
        failures += not _check("GET /leaderboard", r.status_code == 200, str(r.json())[:200])

        # 14. Modes / personalities
        r = c.get(f"{BASE}/api/modes")
        failures += not _check("GET /modes", r.status_code == 200, str(r.json())[:200])
        r = c.get(f"{BASE}/api/personalities")
        failures += not _check("GET /personalities", r.status_code == 200, str(r.json())[:200])

        # 15. Bad auth → 401
        section("Negative tests")
        r = c.get(f"{BASE}/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        failures += not _check("GET /auth/me (bad token) → 401", r.status_code in (401, 403), str(r.status_code))

        # 16. Contact validation
        r = c.post(f"{BASE}/api/v1/contact", json={"name": "x", "email": "bad", "subject": "x", "message": "x"})
        failures += not _check("POST /contact (bad payload) → 422", r.status_code == 422, str(r.status_code))

        # 17. Logout
        r = c.post(f"{BASE}/api/v1/auth/logout", headers=auth)
        failures += not _check("POST /auth/logout", r.status_code in (200, 204), str(r.status_code))

        # 18. Refresh after logout (may fail — that's expected if server revokes)
        r = c.post(f"{BASE}/api/v1/auth/refresh", json={"refresh_token": refresh})
        # Don't fail on this — the server may or may not have a token blocklist.

        # 19. Maintenance mode: enable → non-admin gets 503 → admin gets through
        section("Maintenance mode")
        if "admin_auth" in dir():
            r = c.put(f"{BASE}/api/v1/admin/feature-flags", json={
                "key": "maintenance_mode", "enabled": True,
            }, headers=admin_auth)
            failures += not _check("enable maintenance", r.status_code in (200, 204), str(r.json())[:200])

            r = c.get(f"{BASE}/api/v1/leaderboard")
            failures += not _check("non-admin blocked (503)", r.status_code == 503, str(r.json())[:200])

            r = c.get(f"{BASE}/api/v1/system/status")
            failures += not _check("status still works (200)", r.status_code == 200, str(r.json())[:200])

            r = c.get(f"{BASE}/api/v1/auth/me", headers=admin_auth)
            failures += not _check("admin gets through (200)", r.status_code == 200, str(r.json())[:200])

            # Disable for cleanup
            r = c.put(f"{BASE}/api/v1/admin/feature-flags", json={
                "key": "maintenance_mode", "enabled": False,
            }, headers=admin_auth)
            failures += not _check("disable maintenance", r.status_code in (200, 204), str(r.json())[:200])
        else:
            failures += not _check("maintenance (skipped, no admin token)", True)

    print(f"\n=== Summary ===")
    if failures == 0:
        print(f"All checks passed.")
        return 0
    print(f"{failures} check(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
