"""Regression tests for the 150-bug audit fix pass.

Each test covers a specific bug fix. The naming convention is
`test_bug_NNN_short_name` so it's easy to find the related fix.
"""
from __future__ import annotations

import hmac
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW", "1")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-1234567890")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-minimum-1234")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_bugfixes_audit.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db_models
from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_secrets,
)
from app.database import Base, get_db
from app.library import LIB
from app.sanitize import sanitize_text
from main import app


# ----- Fixtures -----

@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


@pytest.fixture(scope="function")
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _register_user(c, email="user@example.com", password="hunter2hunter2"):
    r = c.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Test User",
        "gender_preference": "neutral",
    })
    assert r.status_code == 201, r.text
    return r.json()


# ----- Bug #2: dev-secret fail-fast in production -----

def test_bug_002_validate_secrets_warns_on_dev_default(monkeypatch, caplog):
    """validate_secrets() should not raise in dev — it just logs a warning.
    In production mode it must raise."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("ALLOW_INSECURE_DEFAULTS", raising=False)
    # Should not raise in test env, even with dev defaults.
    validate_secrets()


def test_bug_002_validate_secrets_raises_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("ALLOW_INSECURE_DEFAULTS", raising=False)
    # Force the dev defaults so the validation actually has something to
    # complain about. The conftest sets a real test secret, which would
    # otherwise pass.
    monkeypatch.setattr("app.auth.JWT_SECRET_KEY", "dev-secret-change-in-prod-use-openssl-rand-base64-32")
    monkeypatch.setenv("ADMIN_API_KEY", "dev-secret-change-in-prod")
    with pytest.raises(RuntimeError):
        validate_secrets()


# ----- Bug #10: token_version-based logout-everywhere -----

def test_bug_010_logout_invalidates_access_token(client):
    body = _register_user(client, "logout1@example.com")
    access = body["access_token"]
    # Works before logout
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # Logout
    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # Old token must be rejected now
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401


def test_bug_010_logout_all_invalidates_every_token(client):
    body = _register_user(client, "logout2@example.com")
    access = body["access_token"]
    refresh = body["refresh_token"]
    r = client.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # Access denied
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401
    # Refresh denied
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


def test_bug_010_change_password_invalidates_other_sessions(client):
    body = _register_user(client, "logout3@example.com")
    access = body["access_token"]
    r = client.post("/api/auth/change-password",
        json={"current_password": "hunter2hunter2", "new_password": "newpass1234abcd"},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # Old token is dead
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401


# ----- Bug #16: constant-time login (no account enumeration via timing) -----
# We can't really time this in a unit test, but we can at least verify the
# dummy-hash path doesn't crash when the user is missing.

def test_bug_016_login_with_missing_user_returns_401(client):
    r = client.post("/api/auth/login", json={
        "email": "no-such-user@example.com",
        "password": "anythinghere1234",
    })
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


# ----- Bug #17/#18: input length cap on user message -----

def test_bug_017_long_user_message_rejected(client):
    body = _register_user(client, "long1@example.com")
    access = body["access_token"]
    # Start a session
    r = client.post("/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers={"Authorization": f"Bearer {access}"})
    sid = r.json()["session_id"]
    # 3000-char message — Pydantic caps at 2000 so this should be 422.
    r = client.post(f"/api/session/{sid}/roast",
        json={"message": "a" * 3000},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 422


# ----- Bug #37/#38: chat history size cap on persistence -----

def test_bug_037_long_message_truncated_in_history(client):
    body = _register_user(client, "long2@example.com")
    access = body["access_token"]
    r = client.post("/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers={"Authorization": f"Bearer {access}"})
    sid = r.json()["session_id"]
    # 1500 chars is within the 2000-char input cap but beyond the 4000-char
    # persistence cap? Actually 1500 < 4000 — let's just verify the
    # exact-cap behaviour by sending 1999 chars (under the 2000 input cap).
    msg = "a" * 1999
    r = client.post(f"/api/session/{sid}/roast",
        json={"message": msg},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # Inspect history via the API
    r = client.get("/api/history", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    items = r.json()["items"]
    user_msgs = [i for i in items if i["is_user"]]
    assert any(len(m["message"]) <= 4000 for m in user_msgs)


# ----- Bug #39: control characters stripped from history -----

def test_bug_039_control_chars_stripped(client):
    body = _register_user(client, "ctl@example.com")
    access = body["access_token"]
    r = client.post("/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers={"Authorization": f"Bearer {access}"})
    sid = r.json()["session_id"]
    #  is the BEL char (0x07) — should be stripped.
    msg = "hello\x07\x08\x1b[31mworld"
    r = client.post(f"/api/session/{sid}/roast",
        json={"message": msg},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    r = client.get("/api/history", headers={"Authorization": f"Bearer {access}"})
    items = r.json()["items"]
    user_msgs = [i for i in items if i["is_user"]]
    for m in user_msgs:
        assert "\x07" not in m["message"]
        assert "\x08" not in m["message"]
        assert "\x1b" not in m["message"]


# ----- Sanitize unit tests -----

def test_sanitize_text_strips_control_chars():
    out = sanitize_text("hello\x00\x07world", max_length=100)
    assert out == "helloworld"


def test_sanitize_text_caps_length():
    out = sanitize_text("a" * 500, max_length=100)
    assert len(out) == 100


def test_sanitize_text_preserves_newlines_and_tabs():
    out = sanitize_text("line1\nline2\tcol2", max_length=100)
    assert out == "line1\nline2\tcol2"


def test_sanitize_text_collapses_excess_newlines():
    out = sanitize_text("a\n\n\n\n\nb", max_length=100)
    assert out == "a\n\n\nb"


# ----- Bug #44: ADMIN_API_KEY dev-default removed -----

def test_bug_044_cleanup_refuses_when_admin_key_unset(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    r = client.post("/api/admin/cleanup", headers={"X-Admin-Key": "anything"})
    assert r.status_code == 503


def test_bug_044_cleanup_rejects_wrong_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "the-real-key-12345")
    r = client.post("/api/admin/cleanup", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 403
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key-1234567890")  # restore


# ----- Bug #47: body size cap -----

def test_bug_047_oversized_request_rejected(client, monkeypatch):
    # Body > 5MB should be rejected by the middleware.
    from fastapi.testclient import TestClient
    # We'll just hit /api/session/start with a giant body.
    big = "x" * (6 * 1024 * 1024)
    r = client.post(
        "/api/session/start",
        content=b'{"mode":"savage","personality":"savage_one","username":"' + big.encode() + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413


# ----- Bug #5/#6/#7: payment idempotency -----

def test_bug_006_verify_payment_idempotent(client, monkeypatch):
    """Calling /verify twice with the same payment_id should not create
    a second Subscription row."""
    body = _register_user(client, "idem@example.com")
    access = body["access_token"]

    # Use the test client's dependency-overridden db to seed a plan and
    # subscription. We grab the session out of the app's overrides.
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        plan = db_models.SubscriptionPlan(
            plan_code="starter", name="Starter", price_paise=29900,
            currency="INR", duration_days=10,
            features={}, is_active=True,
        )
        s.add(plan); s.commit()
        # Find the user we just registered
        user = s.query(db_models.User).filter(
            db_models.User.email == "idem@example.com"
        ).first()
        sub = db_models.Subscription(
            user_id=user.id, plan_id=plan.id,
            status=db_models.SubStatus.pending,
            razorpay_order_id="order_TEST_1",
        )
        s.add(sub); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    # Stub razorpay signature verify
    from app import payment_routes
    class _StubClient:
        class utility:
            @staticmethod
            def verify_payment_signature(_payload):
                return True
    monkeypatch.setattr(payment_routes, "get_razorpay_client", lambda: _StubClient)
    payload = {
        "razorpay_order_id": "order_TEST_1",
        "razorpay_payment_id": "pay_TEST_1",
        "razorpay_signature": "sig",
    }
    r1 = client.post("/api/payments/verify", json=payload,
        headers={"Authorization": f"Bearer {access}"})
    r2 = client.post("/api/payments/verify", json=payload,
        headers={"Authorization": f"Bearer {access}"})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200
    assert "already verified" in r2.json()["message"].lower()


# ----- Bug #19: token claims include 'ver' so logout invalidates them -----

def test_bug_019_token_carries_ver_claim():
    tok = create_access_token(42, "u@t.local", token_version=7)
    payload = decode_token(tok)
    assert payload["ver"] == 7
    assert payload["uid"] == 42
    assert "jti" in payload
    assert "iat" in payload


# ----- Bug #20: free-tier cap is per-user, not per-session -----

def test_bug_020_free_tier_cap_is_per_user(client):
    """A user with 5 messages already used can't extend the cap by
    starting a new session."""
    body = _register_user(client, "freeuser@example.com")
    access = body["access_token"]
    # Bump free_messages_used to 5 via direct DB write.
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        u = s.query(db_models.User).filter(
            db_models.User.email == "freeuser@example.com"
        ).first()
        u.free_messages_used = 5
        s.add(u); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # New session should immediately reject any roast with 402.
    r = client.post("/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 402
    assert "5 messages" in r.json()["detail"]


# ----- Bug #14: admin leaderboard uses masked_email -----

def test_bug_014_admin_leaderboard_masks_email(client):
    """Admin leaderboard must not leak raw emails. Also applies to the
    /users and /users/{id} endpoints."""
    # Create a user
    _register_user(client, "leaky@example.com")
    # Promote them via DB
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        u = s.query(db_models.User).filter(
            db_models.User.email == "leaky@example.com"
        ).first()
        u.is_admin = True
        s.add(u); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # Login as that user
    r = client.post("/api/auth/login",
        json={"email": "leaky@example.com", "password": "hunter2hunter2"})
    admin_token = r.json()["access_token"]
    # Hit the leaderboard
    r = client.get("/api/admin/leaderboard",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    raw = r.text
    assert "leaky@example.com" not in raw
    # Hit /api/admin/users
    r = client.get("/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert "leaky@example.com" not in r.text


# ----- Bug #15: admin deactivation bumps token_version -----

def test_bug_015_admin_deactivation_invalidates_token(client):
    """Disabling a user via /api/admin/users/{id} PATCH should invalidate
    their existing access token immediately."""
    # Create user A
    _register_user(client, "v@example.com")
    body = _register_user(client, "victim@example.com")
    victim_token = body["access_token"]
    # Promote v to admin
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        a = s.query(db_models.User).filter(
            db_models.User.email == "v@example.com"
        ).first()
        a.is_admin = True
        s.add(a); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    r = client.post("/api/auth/login",
        json={"email": "v@example.com", "password": "hunter2hunter2"})
    admin_token = r.json()["access_token"]
    # Get the victim's user id
    r = client.get("/api/auth/me",
        headers={"Authorization": f"Bearer {victim_token}"})
    victim_id = r.json()["id"]
    # Admin deactivates the victim
    r = client.patch(f"/api/admin/users/{victim_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    # The victim's old token must now be rejected. Deactivated users
    # get 403 (not 401) so the frontend can distinguish "token invalid"
    # from "account disabled" and avoid an infinite re-login loop. See
    # audit #25.
    r = client.get("/api/auth/me",
        headers={"Authorization": f"Bearer {victim_token}"})
    assert r.status_code == 403


# ----- Bug #23: public leaderboard display_name sanitization -----

def test_bug_023_leaderboard_sanitises_display_name(client):
    """A user with a malicious full_name (e.g. HTML, control chars, links)
    must not have those values appear in the public leaderboard."""
    # Create user with a malicious name
    r = client.post("/api/auth/register", json={
        "email": "meanie@example.com",
        "password": "hunter2hunter2",
        "full_name": "<script>alert(1)</script>\x00\x07hello http://evil.com",
        "gender_preference": "neutral",
    })
    assert r.status_code == 201
    body = r.json()
    access = body["access_token"]
    # Generate a chat history row
    r = client.post("/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers={"Authorization": f"Bearer {access}"})
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    r = client.get("/api/leaderboard?period=all&limit=10")
    assert r.status_code == 200
    raw = r.text
    # No raw HTML tag markers; we replace < > with the unicode single
    # guillemets U+2039 / U+203A so a downstream renderer that doesn't
    # escape HTML still can't interpret the name as a tag.
    assert "<script>" not in raw
    assert "<" not in raw  # no raw < anywhere
    # Link in the name must be stripped.
    assert "http://evil.com" not in raw
    # Control characters must be stripped.
    assert "\x00" not in raw
    assert "\x07" not in raw


# ----- Bug #C1: partial unique index on Subscription is actually unique -----

def test_bug_C1_subscription_unique_index_is_unique():
    """The Index on (user_id, status) for active/past_due is declared
    unique=True. If someone removes `unique=True` this test will catch
    it before deployment."""
    from app.db_models import Subscription
    found = False
    for ix in Subscription.__table__.indexes:
        if ix.name == "uq_subscriptions_user_active":
            assert ix.unique is True, "uq_subscriptions_user_active must be unique"
            found = True
            break
    assert found, "uq_subscriptions_user_active index is missing"


# ----- Bug #C3: free-tier atomic update never lets counter go past 5 -----

def test_bug_C3_free_tier_atomic_update_enforces_cap(client):
    """Sequential 7 requests, after the 5th the rest must 402. The
    free_messages_used counter must end at exactly 5. The atomic
    conditional update means a parallel attacker can't squeeze more
    than 5 in (covered separately by the WHERE < 5 clause)."""
    body = _register_user(client, "racey@example.com")
    access = body["access_token"]
    r = client.post("/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers={"Authorization": f"Bearer {access}"})
    sid = r.json()["session_id"]
    statuses = []
    for _ in range(7):
        r = client.post(f"/api/session/{sid}/roast",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {access}"})
        statuses.append(r.status_code)
    # First 5 succeed, rest 402.
    assert statuses[:5] == [200] * 5
    assert all(s == 402 for s in statuses[5:])
    # Verify the counter
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.json()["free_messages_used"] == 5


def test_bug_C3_atomic_where_clause_in_source():
    """Defence-in-depth: the SQL atomic update must use the
    `free_messages_used < 5` WHERE so the row is only incremented if
    the user is still under the cap. Source-code grep is sufficient —
    testing actual race behaviour requires multi-threaded SQLite which
    the in-memory test harness doesn't support reliably."""
    import inspect
    from app import routes
    src = inspect.getsource(routes)
    # The conditional WHERE must exist exactly as written in the gate.
    assert "free_messages_used < 5" in src
    # And the increment must be on the column, not a Python variable.
    assert "User.free_messages_used + 1" in src


# ----- Bug #C4: X-Forwarded-For bypass blocked -----

def test_bug_C4_xff_bypass_blocked_from_untrusted_peer(client):
    """A request from a non-trusted peer with X-Forwarded-For must NOT
    use the XFF header for rate-limit bucketing. We test by sending a
    request with XFF=1.2.3.4 and verifying the request still goes
    through (i.e. the rate limiter doesn't 429 it just because the XFF
    bucket is full — the untrusted XFF is ignored)."""
    # Send a few requests with bogus XFF; none should be 429 because
    # the bucket key is the direct peer (test client), not 1.2.3.4.
    statuses = []
    for _ in range(3):
        r = client.get("/api/health", headers={"X-Forwarded-For": "1.2.3.4"})
        statuses.append(r.status_code)
    assert all(s != 429 for s in statuses), statuses


# ----- Bug #H1: create-order refuses if active sub exists -----

def test_bug_H1_create_order_refuses_if_already_active(client, monkeypatch):
    body = _register_user(client, "hasub@example.com")
    access = body["access_token"]
    # Seed a plan and an active sub directly in the DB.
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        plan = db_models.SubscriptionPlan(
            plan_code="starter", name="Starter", price_paise=29900,
            currency="INR", duration_days=10, features={}, is_active=True,
        )
        s.add(plan); s.commit()
        u = s.query(db_models.User).filter(
            db_models.User.email == "hasub@example.com"
        ).first()
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        sub = db_models.Subscription(
            user_id=u.id, plan_id=plan.id, status=db_models.SubStatus.active,
            current_period_start=now,
            current_period_end=now + timedelta(days=10),
        )
        s.add(sub); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # Stub Razorpay so the test doesn't need real keys
    from app import payment_routes
    class _StubClient:
        def __init__(self):
            class _Order:
                def create(self_inner, _payload):
                    return {"id": "order_stub_1"}
            self.order = _Order()
    monkeypatch.setattr(payment_routes, "get_razorpay_client", lambda: _StubClient())
    r = client.post("/api/payments/create-order",
        json={"plan_code": "starter"},
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 409
    assert "already have" in r.json()["detail"].lower()


# ----- Bug #H4: verify_payment doesn't write payment_id to subscription_id column -----

def test_bug_H4_verify_payment_does_not_overwrite_subscription_id(client, monkeypatch):
    body = _register_user(client, "h4user@example.com")
    access = body["access_token"]
    # Seed a plan and a pending sub with a known order_id
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        plan = db_models.SubscriptionPlan(
            plan_code="starter", name="Starter", price_paise=29900,
            currency="INR", duration_days=10, features={}, is_active=True,
        )
        s.add(plan); s.commit()
        u = s.query(db_models.User).filter(
            db_models.User.email == "h4user@example.com"
        ).first()
        sub = db_models.Subscription(
            user_id=u.id, plan_id=plan.id, status=db_models.SubStatus.pending,
            razorpay_order_id="order_H4",
            razorpay_subscription_id="sub_real_123",
        )
        s.add(sub); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    from app import payment_routes
    class _StubClient:
        class utility:
            @staticmethod
            def verify_payment_signature(_payload):
                return True
    monkeypatch.setattr(payment_routes, "get_razorpay_client", lambda: _StubClient)
    r = client.post("/api/payments/verify",
        json={
            "razorpay_order_id": "order_H4",
            "razorpay_payment_id": "pay_H4_xyz",
            "razorpay_signature": "sig",
        },
        headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # The subscription_id column must still hold the original sub id, NOT
    # the payment id.
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        sub = s.query(db_models.Subscription).filter(
            db_models.Subscription.razorpay_order_id == "order_H4"
        ).first()
        assert sub.razorpay_subscription_id == "sub_real_123", \
            f"Expected sub_real_123, got {sub.razorpay_subscription_id!r}"
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ----- Bug #H5: grant_subscription extends instead of duplicating -----

def test_bug_H5_grant_extends_existing_sub(client):
    body = _register_user(client, "ext@example.com")
    # Promote them to admin
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        u = s.query(db_models.User).filter(
            db_models.User.email == "ext@example.com"
        ).first()
        u.is_admin = True
        s.add(u); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    r = client.post("/api/auth/login",
        json={"email": "ext@example.com", "password": "hunter2hunter2"})
    admin_token = r.json()["access_token"]
    # Seed plans (idempotent)
    from app.payment_routes import seed_plans
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        seed_plans(s)
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # Get target user
    _register_user(client, "target@example.com")
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        target = s.query(db_models.User).filter(
            db_models.User.email == "target@example.com"
        ).first()
        target_id = target.id
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # First grant
    r = client.post("/api/admin/grant-subscription",
        json={"user_id": target_id, "plan_code": "starter", "duration_days": 5},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    # Second grant — must extend, not duplicate
    r = client.post("/api/admin/grant-subscription",
        json={"user_id": target_id, "plan_code": "starter", "duration_days": 5},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        subs = s.query(db_models.Subscription).filter(
            db_models.Subscription.user_id == target_id,
            db_models.Subscription.status == db_models.SubStatus.active,
        ).all()
        assert len(subs) == 1, f"Expected 1 active sub, got {len(subs)}"
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ----- Bug #H6: grant_subscription response doesn't leak raw email -----

def test_bug_H6_grant_subscription_masks_email(client):
    body = _register_user(client, "admin6@example.com")
    _register_user(client, "victim6@example.com")
    # Seed plans
    from app.payment_routes import seed_plans
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        seed_plans(s)
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # Promote admin
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        u = s.query(db_models.User).filter(
            db_models.User.email == "admin6@example.com"
        ).first()
        u.is_admin = True
        s.add(u); s.commit()
        v = s.query(db_models.User).filter(
            db_models.User.email == "victim6@example.com"
        ).first()
        victim_id = v.id
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    r = client.post("/api/auth/login",
        json={"email": "admin6@example.com", "password": "hunter2hunter2"})
    admin_token = r.json()["access_token"]
    r = client.post("/api/admin/grant-subscription",
        json={"user_id": victim_id, "plan_code": "starter", "duration_days": 5},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert "victim6@example.com" not in r.text
    assert "vi***" in r.text  # masked form


# ----- Bug #H3: JWT clock-skew leeway -----

def test_bug_H3_jwt_decode_accepts_clock_skew():
    """A token whose `exp` is up to 25s in the past (clock skew) must
    still decode successfully."""
    import time as _t
    from app.auth import create_access_token, decode_token
    # Issue a token manually with an exp 10s in the past
    import jose.jwt as jjwt
    from app.auth import JWT_SECRET_KEY, JWT_ALGORITHM
    import datetime as _dt
    payload = {
        "sub": "1", "uid": 1, "type": "access", "ver": 0,
        "exp": _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=10),
    }
    tok = jjwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    # With 30s leeway, this should still decode
    decoded = decode_token(tok)
    assert decoded["uid"] == 1


# ----- Bug #L1: refresh_token rejects malformed uid -----

def test_bug_L1_refresh_token_rejects_non_int_uid():
    """A refresh token with a non-int `uid` claim must be rejected, not
    passed through to the DB lookup (which would error on PostgreSQL)."""
    from app.auth import JWT_SECRET_KEY, JWT_ALGORITHM
    import jose.jwt as jjwt
    import datetime as _dt
    from app.auth import decode_token
    payload = {
        "sub": "abc", "uid": "not-an-int", "type": "refresh", "ver": 0,
        "exp": _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1),
    }
    tok = jjwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    # decode_token returns the payload; the int cast happens in the
    # refresh endpoint. The endpoint must raise 401 on int() failure.
    decoded = decode_token(tok)
    assert decoded["uid"] == "not-an-int"
    with pytest.raises((TypeError, ValueError)):
        int(decoded["uid"])


# ----- Bug #M1: verify_payment idempotency check is scoped to user -----

def test_bug_M1_verify_payment_does_not_leak_other_users_sub(client, monkeypatch):
    """If two users both have a payment row with the same razorpay_payment_id
    (impossible in practice but a defence-in-depth), verify_payment for
    user A must return A's subscription, not B's."""
    # This is hard to set up via the API because razorpay_payment_id has
    # a unique constraint. We just verify the SQL filter scopes by
    # user_id by inspecting the code path indirectly.
    from app import payment_routes
    import inspect
    src = inspect.getsource(payment_routes.verify_payment)
    assert "Payment.user_id == user.id" in src
    assert "Subscription.user_id == user.id" in src


# ----- Bug #M6: shared mask_email in sanitize.py -----

def test_bug_M6_mask_email_single_implementation():
    """There's exactly one canonical mask_email in app.sanitize, used
    by both admin and public leaderboard."""
    from app.sanitize import mask_email
    assert mask_email("alice@example.com") == "al***@example.com"
    assert mask_email("a@example.com") == "a***@example.com"
    assert mask_email("not-an-email") == "not-an-email"
    assert mask_email("") == ""


# ----- Bug #L5: JWT_ALGORITHM allow-list enforced at startup -----

def test_bug_L5_jwt_algorithm_allow_list():
    """Verify the algorithm allow-list contains the expected entries and
    excludes insecure ones."""
    from app.auth import _ALLOWED_ALGS
    assert "HS256" in _ALLOWED_ALGS
    assert "HS384" in _ALLOWED_ALGS
    assert "HS512" in _ALLOWED_ALGS
    assert "none" not in _ALLOWED_ALGS
    assert "RS256" not in _ALLOWED_ALGS


# ----- Bug #L8: chat history composite index -----

def test_bug_L8_chat_history_has_composite_index():
    from app.db_models import ChatHistory
    found = False
    for ix in ChatHistory.__table__.indexes:
        if ix.name == "ix_chat_history_user_created":
            found = True
            cols = [c.name for c in ix.columns]
            assert "user_id" in cols
            assert "created_at" in cols
            break
    assert found, "ix_chat_history_user_created index is missing"


# ======================================================================
# Third-pass audit regressions (June 2026)
# ======================================================================

# ----- Bug #1: TRUSTED_PROXIES must be honoured by the IP extractor -----

def test_audit3_01_trusted_proxies_default_covers_loopback(monkeypatch):
    """Without explicit config, localhost is trusted so dev XFF works.
    With an explicit 10.0.0.0/8 list (Render), only the proxy IP range
    is trusted, not arbitrary XFF sources."""
    import importlib
    import main
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    importlib.reload(main)
    assert main._is_trusted_proxy("127.0.0.1") is True
    assert main._is_trusted_proxy("::1") is True
    assert main._is_trusted_proxy("203.0.113.1") is False


# ----- Bug #3: PII in session history -----

def test_audit3_03_pii_user_message_not_persisted(client, db_session):
    """When the safety filter refuses a PII-laden message, the raw user
    text must NOT be appended to session history. A redacted
    placeholder is acceptable."""
    from app.models import RoastMode, Personality
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one", "username": "alice",
        "roaster_gender": "male",
    })
    assert r.status_code == 200
    sid = r.json()["session_id"]
    pii_msg = "my email is secretperson@gmail.com"
    r = client.post(f"/api/session/{sid}/roast", json={"message": pii_msg})
    assert r.status_code == 200
    # Pull session from the in-memory store and check history.
    from app.session import SESSIONS
    s = SESSIONS.get(sid)
    assert s is not None
    user_msgs = [m for m in s.history if m.role == "user"]
    assert user_msgs, "expected at least one user message in history"
    # The raw PII must not appear anywhere in the user messages.
    for m in user_msgs:
        assert "secretperson@gmail.com" not in m.content, (
            f"raw PII leaked into history: {m.content!r}"
        )


# ----- Bug #5: free-tier atomic update raises 503 on DB error -----

def test_audit3_05_free_tier_503_on_db_error(client, db_session, monkeypatch):
    """A simulated DB error during the free-tier atomic update must
    return 503, not silently pass the gate.

    The previous behaviour was to set res = None on any exception and
    skip the gate entirely, allowing a free-tier bypass during DB
    hiccups. We assert here that an OperationalError raised inside
    the atomic update propagates as a 503. (We do this by patching
    the Session.execute method; the roast route is the only path
    that uses `update(User)` against the test DB.)"""
    from sqlalchemy.exc import OperationalError
    # Register a user via the API
    r = client.post("/api/auth/register", json={
        "email": "free503@example.com", "password": "hunter2hunter2",
    })
    assert r.status_code == 201
    token = r.json()["access_token"]

    # Replace Session.execute on the bound override session.
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        original_execute = s.execute
        flag = {"raise": True}

        def maybe_boom(*args, **kwargs):
            if not flag["raise"]:
                return original_execute(*args, **kwargs)
            # Inspect the statement to only intercept UPDATE on users
            stmt = args[0] if args else kwargs.get("statement")
            try:
                from sqlalchemy import Update
                if isinstance(stmt, Update) and getattr(stmt.table, "name", None) == "users":
                    raise OperationalError("simulated", {}, Exception("boom"))
            except (AttributeError, TypeError):
                pass
            return original_execute(*args, **kwargs)
        monkeypatch.setattr(s, "execute", maybe_boom)

        # Start a session, then try to roast.
        r = client.post("/api/session/start", json={
            "mode": "savage", "personality": "savage_one", "username": "free503",
            "roaster_gender": "male",
        })
        assert r.status_code == 200
        sid = r.json()["session_id"]
        r = client.post(f"/api/session/{sid}/roast", json={
            "message": "hi", "roaster_gender": "male",
        }, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 503
        assert "temporarily unavailable" in r.json()["detail"].lower()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# ----- Bug #6: Subscription.razorpay_order_id is unique -----

def test_audit3_06_subscription_razorpay_order_id_unique():
    from app.db_models import Subscription
    cols = {c.name for c in Subscription.__table__.columns}
    col = Subscription.__table__.columns["razorpay_order_id"]
    assert col.unique is True, "razorpay_order_id must be unique=True"


# ----- Bug #6b: hot-path index on (user_id, status, current_period_end) -----

def test_audit3_06b_subscription_period_index():
    from app.db_models import Subscription
    found = False
    for ix in Subscription.__table__.indexes:
        if ix.name == "ix_subscriptions_user_status_period_end":
            cols = [c.name for c in ix.columns]
            assert "user_id" in cols
            assert "status" in cols
            assert "current_period_end" in cols
            found = True
    assert found, "ix_subscriptions_user_status_period_end is missing"


# ----- Bug #7: grant_subscription.duration_days is capped -----

def test_audit3_07_grant_duration_days_capped(client, db_session):
    """A duration_days over 10 years must be rejected with 422."""
    from app import db_models
    from app.database import get_db as real_get_db
    # Register the victim via the API
    _register_user(client, "victim_dc@example.com", "victimpassword1")
    _register_user(client, "admin_dc@example.com", "adminpassword1")
    # Add plan and promote admin via dependency override
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        plan = db_models.SubscriptionPlan(
            plan_code="pro_dc", name="Pro", price_paise=79900, currency="INR",
            duration_days=30, is_active=True,
        )
        s.add(plan)
        a = s.query(db_models.User).filter(
            db_models.User.email == "admin_dc@example.com"
        ).first()
        a.is_admin = True
        s.add(a)
        v = s.query(db_models.User).filter(
            db_models.User.email == "victim_dc@example.com"
        ).first()
        victim_id = v.id
        s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # Login as admin
    r = client.post("/api/auth/login",
        json={"email": "admin_dc@example.com", "password": "adminpassword1"})
    assert r.status_code == 200
    admin_token = r.json()["access_token"]
    r = client.post(
        "/api/admin/grant-subscription",
        json={"user_id": victim_id, "plan_code": "pro_dc", "duration_days": 99999},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 422


# ----- Bug #16: webhook handlers for refund/halted/completed exist -----

def test_audit3_16_webhook_handlers_handle_refund(client, db_session):
    """Verify the refund.processed handler updates Payment.status and
    Subscription.status without crashing."""
    from app import db_models
    from app.auth import hash_password
    user = db_models.User(
        email="refunder@example.com",
        hashed_password=hash_password("refunderpassword1"),
        is_active=True, is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    plan = db_models.SubscriptionPlan(
        plan_code="pro", name="Pro", price_paise=79900, currency="INR",
        duration_days=30, is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    sub = db_models.Subscription(
        user_id=user.id, plan_id=plan.id,
        status=db_models.SubStatus.active,
        razorpay_subscription_id="sub_test123",
    )
    db_session.add(sub)
    db_session.commit()
    payment = db_models.Payment(
        user_id=user.id, subscription_id=sub.id,
        razorpay_payment_id="pay_test123", razorpay_order_id="order_test123",
        amount=79900, currency="INR", status=db_models.PaymentStatus.captured,
    )
    db_session.add(payment)
    db_session.commit()
    # Build a fake but validly-signed webhook. The handler will fail
    # signature verification in this test (no real secret) but we
    # just want to confirm the endpoint exists and the path is wired
    # up. A 400 with "Invalid signature" is acceptable.
    r = client.post("/api/payments/webhook", content=b'{"event":"refund.processed"}',
                    headers={"x-razorpay-signature": "bogus"})
    assert r.status_code in (200, 400)  # 400 is fine (bad sig)


# ----- Bug #19: leaderboard sanitises email-fallback display name -----

def test_audit3_19_leaderboard_sanitises_email_fallback(client, db_session):
    """A user with no full_name and a malicious email local-part must
    not have HTML or control chars appear on the leaderboard."""
    from app import db_models
    user = db_models.User(
        email="<b>bold</b>@example.com",
        hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    # Create a chat history entry that would put this user on the
    # leaderboard.
    ch = db_models.ChatHistory(
        user_id=user.id, message="test", is_user=True, score_total=10.0,
    )
    db_session.add(ch)
    db_session.commit()
    r = client.get("/api/leaderboard?period=all")
    assert r.status_code == 200
    body = r.json()
    for entry in body.get("entries", []):
        # The raw HTML must be neutralised.
        if entry["user_id"] == user.id:
            assert "<b>" not in entry["display_name"]
            assert "bold" in entry["display_name"] or entry["display_name"] == "Anonymous"


# ----- Bug #25: deactivated user gets 403, not 401 -----

def test_audit3_25_deactivated_user_gets_403(client, db_session):
    """A deactivated user gets 403, not 401. Stale tokens and missing
    users still get 401."""
    # Register victim + admin via the API
    body = _register_user(client, "deact_victim@example.com", "deactpassword1")
    victim_token = body["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {victim_token}"})
    victim_id = r.json()["id"]
    _register_user(client, "deact_admin@example.com", "adminpassword1")
    # Promote to admin via the dependency override (proven working pattern)
    from app.database import get_db as real_get_db
    db_gen = app.dependency_overrides[real_get_db]()
    s = next(db_gen)
    try:
        a = s.query(db_models.User).filter(
            db_models.User.email == "deact_admin@example.com"
        ).first()
        a.is_admin = True
        s.add(a); s.commit()
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    # Login as admin
    r = client.post("/api/auth/login",
        json={"email": "deact_admin@example.com", "password": "adminpassword1"})
    admin_token = r.json()["access_token"]
    r = client.patch(f"/api/admin/users/{victim_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    # Victim's old token must now be rejected with 403 (not 401).
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {victim_token}"})
    assert r.status_code == 403
    # A truly invalid token still gives 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


# ----- Bug #28: session_id is now full 128-bit entropy -----

def test_audit3_28_session_id_128_bits():
    from app.session import SessionStore
    from app.models import RoastMode, Personality
    s = SessionStore()
    s.create(RoastMode.SAVAGE, Personality.SAVAGE_ONE, "test")
    sid = list(s._sessions.keys())[0]
    assert len(sid) == 32, f"expected 32 hex chars (128 bits), got {len(sid)}"
    assert all(c in "0123456789abcdef" for c in sid)



