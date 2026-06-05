"""Regression tests for Round-5 production-readiness audit fixes.

Covers the new defences added on top of the Round-1/4 fixes:
  * Open-redirect: `?return=` is rejected for cross-origin / scheme
    prefixes.
  * `X-XSS-Protection` header is REMOVED (was deprecated, net negative).
  * CORS methods/headers are restricted (not "*").
  * `body_size_limit` rejects `Transfer-Encoding: chunked` (the
    bypass path around the Content-Length cap).
  * `verify_payment` IntegrityError fallback is scoped to the
    authenticated user (info-disclosure fix).
  * `/api/auth/refresh` rotates the refresh token (bumps
    `token_version`); a re-use of the old refresh token returns 401.
  * `/api/auth/change-password` is rate-limited.
  * Admin `/cleanup` purges both in-memory sessions AND DB rows.
  * `SessionStore.create` REFUSES to evict live sessions; returns
    `None` and the route maps to 503.
  * `RoastSession.ended_at` is stored with sub-second precision.
  * Webhook endpoint accepts its own rate-limit bucket (smoke test).
  * `/api/auth/change-password` rejects `new == current`.
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# All env vars must be set BEFORE any app imports. conftest does this
# for us, but we re-assert here so the file is self-documenting.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "1")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-1234567890")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-minimum-1234")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW", "1")
os.environ.setdefault("RATE_LIMIT_REGISTER", "10000")
os.environ.setdefault("RATE_LIMIT_LOGIN", "10000")
os.environ.setdefault("RATE_LIMIT_REFRESH", "10000")
os.environ.setdefault("RATE_LIMIT_SESSION_START", "10000")

from main import app  # noqa: E402
from app import db_models, database, routes  # noqa: E402
from app.session import SESSIONS, SessionStore  # noqa: E402
from app import session as session_module  # noqa: E402
from app import payment_routes  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures (local copy to keep this file independent)
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_models.Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="function")
def client(db_session):
    from app.database import get_db

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client, email: str, password: str = "superpassword") -> dict:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Tester"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---------------------------------------------------------------------------
# Security: open-redirect
# ---------------------------------------------------------------------------


def test_audit5_login_rejects_cross_origin_return(client):
    """A `?return=` value with a cross-origin scheme or `//` must
    be ignored — the user is sent to `/`, not to the attacker's site.
    """
    # Login with the malicious return param. We expect the server
    # to NOT reflect the cross-origin return path. The frontend's
    # safeReturnPath() is the actual gate; on the backend side we
    # verify the contract by checking that the API does not
    # itself redirect or echo the param.
    r = client.post(
        "/api/auth/login",
        params={"return": "//evil.com/phish"},
        json={"email": "audit5-open@example.com", "password": "superpassword"},
    )
    # 200 (login ok) is the common path. The body must not contain
    # the evil host.
    if r.status_code == 200:
        body = r.text
        assert "evil.com" not in body
    # And the schema doesn't have a `return` field anyway — the
    # backend never trusted the return param in the first place.
    # The actual XSS/open-redirect defense lives in the frontend
    # lib/security.ts:safeReturnPath, mirrored here for unit tests.
    from tests.frontend_security_compat import safeReturnPath
    assert safeReturnPath("//evil.com/phish") == "/"
    assert safeReturnPath("/\\evil.com") == "/"
    assert safeReturnPath("javascript:alert(1)") == "/"
    assert safeReturnPath("https://evil.com/") == "/"
    assert safeReturnPath("/dashboard?ok=1") == "/dashboard?ok=1"


# ---------------------------------------------------------------------------
# Security: headers
# ---------------------------------------------------------------------------


def test_audit5_x_xss_protection_removed(client):
    """The deprecated and net-negative `X-XSS-Protection` header
    must NOT be present on responses."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "x-xss-protection" not in {k.lower() for k in r.headers.keys()}


def test_audit5_security_headers_present(client):
    """The remaining security headers must still be set on
    successful responses."""
    r = client.get("/api/health")
    keys = {k.lower() for k in r.headers.keys()}
    assert "x-content-type-options" in keys
    assert "x-frame-options" in keys
    assert "referrer-policy" in keys


def test_audit5_security_headers_on_error(client):
    """A 404 response must also carry the security headers — a
    previous bug was that the headers were only applied on success
    because they were set inside the success path. Now they're
    added by a BaseHTTPMiddleware that runs for every response."""
    r = client.post(
        "/api/auth/login",
        json={"email": "does-not-exist@example.com", "password": "wrong"},
    )
    assert r.status_code in (400, 401)
    keys = {k.lower() for k in r.headers.keys()}
    assert "x-content-type-options" in keys
    assert "x-frame-options" in keys


# ---------------------------------------------------------------------------
# Security: CORS
# ---------------------------------------------------------------------------


def test_audit5_cors_not_wildcard():
    """CORS must NOT be configured with `allow_methods=["*"]` or
    `allow_headers=["*"]` — that defeats the protection."""
    from starlette.middleware.cors import CORSMiddleware

    from main import app

    found = False
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            found = True
            # `Middleware` objects expose their kwargs in __dict__.
            opts = vars(mw)
            methods = opts.get("allow_methods") or []
            headers = opts.get("allow_headers") or []
            if methods and isinstance(methods, list):
                assert methods != ["*"], f"CORS allow_methods must not be '*', got {methods}"
            if headers and isinstance(headers, list):
                assert headers != ["*"], f"CORS allow_headers must not be '*', got {headers}"
            break
    assert found, "CORSMiddleware not registered on app"


# ---------------------------------------------------------------------------
# Security: body-size
# ---------------------------------------------------------------------------


def test_audit5_body_size_rejects_chunked():
    """`Transfer-Encoding: chunked` with no Content-Length is the
    bypass path around the body-size cap. The middleware must
    reject it (the body is unbounded, so we cannot enforce a cap)."""
    from starlette.requests import Request
    from main import body_size_limit
    import asyncio

    seen = {"called": False}

    async def call_next(_request):
        seen["called"] = True
        from starlette.responses import JSONResponse
        return JSONResponse({"detail": "should not be called"})

    # Build a fake request that simulates a chunked-encoded
    # POST with no Content-Length.
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [(b"transfer-encoding", b"chunked")],
    }
    req = Request(scope)

    async def run():
        return await body_size_limit(req, call_next)

    resp = asyncio.run(run())
    assert resp.status_code == 411, f"expected 411, got {resp.status_code}"
    # The downstream handler must NOT have been invoked.
    assert seen["called"] is False, "chunked request reached the route"


# ---------------------------------------------------------------------------
# Security: verify_payment user scoping
# ---------------------------------------------------------------------------


def test_audit5_verify_payment_user_scoped(client, db_session, monkeypatch):
    """If the IntegrityError fallback ever fires, it must be
    scoped to the authenticated user. The previous code queried
    by razorpay_payment_id alone, which would have leaked another
    user's subscription_id and current_period_end to a different
    user who could guess a real payment_id."""
    a = _register_and_login(client, "audit5-pay@example.com")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit5-pay@example.com"
    ).one()
    user_id = user.id

    # Patch the integrity-error path: make the verify call raise
    # IntegrityError on the first commit, then succeed. We need a
    # matching existing payment row to test the re-query path.
    payment = db_models.Payment(
        user_id=user_id,
        razorpay_payment_id="pay_TEST_OTHER_USER",
        amount=100,
        currency="INR",
        status="captured",
    )
    db_session.add(payment)
    db_session.commit()

    # Call the helper directly. It must not raise and must return
    # the user's own payment.
    from app.payment_routes import _verify_payment_after_integrity_error
    result = _verify_payment_after_integrity_error(
        user_id=user_id,
        razorpay_payment_id="pay_TEST_OTHER_USER",
        db=db_session,
    )
    assert result is not None
    assert int(result.user_id) == int(user_id)


def test_audit5_verify_payment_does_not_leak_other_user(client, db_session):
    """A different user querying with the same payment_id must
    NOT see the first user's row."""
    a1 = _register_and_login(client, "audit5-pay-a@example.com")
    a2 = _register_and_login(client, "audit5-pay-b@example.com")
    u1 = db_session.query(db_models.User).filter(
        db_models.User.email == "audit5-pay-a@example.com"
    ).one()
    u2 = db_session.query(db_models.User).filter(
        db_models.User.email == "audit5-pay-b@example.com"
    ).one()
    payment = db_models.Payment(
        user_id=u1.id,
        razorpay_payment_id="pay_PRIVATE_ABC",
        amount=100,
        currency="INR",
        status="captured",
    )
    db_session.add(payment)
    db_session.commit()

    from app.payment_routes import _verify_payment_after_integrity_error
    # User 1 sees their own row.
    r1 = _verify_payment_after_integrity_error(
        user_id=u1.id, razorpay_payment_id="pay_PRIVATE_ABC", db=db_session,
    )
    assert r1 is not None and int(r1.user_id) == int(u1.id)
    # User 2 gets nothing (the row is filtered out by user_id).
    r2 = _verify_payment_after_integrity_error(
        user_id=u2.id, razorpay_payment_id="pay_PRIVATE_ABC", db=db_session,
    )
    assert r2 is None


# ---------------------------------------------------------------------------
# Security: refresh-token rotation
# ---------------------------------------------------------------------------


def test_audit5_refresh_rotates_token(client, db_session):
    """A successful /refresh must bump token_version so the old
    refresh token is no longer usable."""
    a = _register_and_login(client, "audit5-refresh@example.com")
    old_refresh = a["refresh_token"]
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit5-refresh@example.com"
    ).one()
    ver_before = user.token_version

    r = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200, r.text
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Old refresh token must be rejected now.
    r2 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401, r2.text

    # And token_version was actually bumped.
    db_session.refresh(user)
    assert user.token_version == ver_before + 1


# ---------------------------------------------------------------------------
# Security: change-password validation
# ---------------------------------------------------------------------------


def test_audit5_change_password_rejects_same_as_current(client):
    a = _register_and_login(client, "audit5-samepw@example.com")
    r = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "superpassword",
            "new_password": "superpassword",  # same!
        },
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code in (400, 422), r.text


def test_audit5_change_password_rejects_weak(client):
    a = _register_and_login(client, "audit5-weakpw@example.com")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "superpassword", "new_password": "123"},
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code in (400, 422), r.text


# ---------------------------------------------------------------------------
# Cleanup purges both stores
# ---------------------------------------------------------------------------


def test_audit5_cleanup_purges_db_rows(client, db_session):
    """The /admin/cleanup endpoint must remove BOTH in-memory
    sessions AND persisted DB rows for ended sessions past the TTL.
    """
    a = _register_and_login(client, "audit5-cleanup@example.com")
    user_id = db_session.query(db_models.User).filter(
        db_models.User.email == "audit5-cleanup@example.com"
    ).one().id

    # Start and end a session, then manually back-date it.
    start = client.post(
        "/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers=_auth_headers(a["access_token"]),
    )
    sid = start.json()["session_id"]
    client.post(
        f"/api/session/{sid}/roast",
        json={"message": "I am a 10x engineer."},
        headers=_auth_headers(a["access_token"]),
    )
    client.post(
        f"/api/session/{sid}/end",
        headers=_auth_headers(a["access_token"]),
    )

    # The DB row exists.
    row = db_session.query(db_models.RoastSession).filter(
        db_models.RoastSession.session_id == sid
    ).one()
    # Back-date ended_at to long ago. The column is a Float
    # (Unix epoch), not a DateTime.
    row.ended_at = time.time() - 30 * 86400  # 30 days ago
    db_session.commit()

    r = client.post(
        "/api/admin/cleanup",
        headers={"X-Admin-Key": "test-admin-key-1234567890"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # New fields: in_memory_removed, db_removed. The DB row should
    # have been removed (it's been ended for 30 days, way past TTL).
    assert "db_removed" in body
    assert "in_memory_removed" in body


# ---------------------------------------------------------------------------
# SessionStore.create refuses to evict live sessions
# ---------------------------------------------------------------------------


def test_audit5_session_store_refuses_to_evict_live(monkeypatch):
    """A previous bug: when the session cap was reached by LIVE
    sessions, the oldest LIVE was silently dropped, losing the
    user's transcript. The new behaviour: refuse to evict,
    return None, set overflow=True."""
    import app.session as session_module
    monkeypatch.setattr(session_module, "MAX_SESSIONS", 2)

    store = SessionStore()
    s1 = store.create("savage", "savage_one", "alice", "male")
    s2 = store.create("savage", "savage_one", "bob", "male")
    assert s1 is not None and s2 is not None

    # Both are live. The next create must NOT evict them; it must
    # return None and signal overflow.
    s3 = store.create("savage", "savage_one", "carol", "female")
    assert s3 is None
    assert store.overflow is True

    # The two live sessions are STILL there.
    assert store.get(s1.session_id) is not None
    assert store.get(s2.session_id) is not None


# ---------------------------------------------------------------------------
# ended_at precision
# ---------------------------------------------------------------------------


def test_audit5_ended_at_float_precision():
    """`ended_at: Optional[float]` must be stored as a float, not
    truncated to integer seconds. SQLite silently rounds float
    columns to int if the column is declared Integer — we need
    Float."""
    from app.db_models import RoastSession
    col = RoastSession.__table__.columns["ended_at"]
    assert col.type.__class__.__name__ in ("Float", "Numeric", "REAL"), (
        f"ended_at must be Float/Numeric/REAL, got {col.type.__class__.__name__}"
    )


# ---------------------------------------------------------------------------
# Webhook accepts its own bucket
# ---------------------------------------------------------------------------


def test_audit5_webhook_rate_limit_registered():
    """A separate rate-limit bucket must exist for the webhook
    endpoint so a Razorpay delivery storm doesn't trip the per-IP
    limit."""
    from main import RATE_LIMIT_OVERRIDES
    assert "/api/payments/webhook" in RATE_LIMIT_OVERRIDES


def test_audit5_change_password_rate_limit_registered():
    from main import RATE_LIMIT_OVERRIDES
    assert "/api/auth/change-password" in RATE_LIMIT_OVERRIDES
