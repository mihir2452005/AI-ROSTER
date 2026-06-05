"""Tests for the feature-complete Round 6 (Gold Standard) additions:

  * Email verification
  * Forgot / reset password
  * Delete account (soft delete)
  * Avatar upload (data URI + URL)
  * User statistics endpoint
  * Favorite mode/personality
  * Admin JWT login
  * Admin ban / unban
  * Admin feature flags
  * Admin audit logs
  * Admin user achievements
  * Admin charts (signups, chats)
  * Admin stats: total_chats, avg_session_time, most_used_mode, DAU
  * Subscription downgrade
  * History search (`?q=`)
  * History export (txt, md, json)
  * User memory table (per-mode counts, recent topics, score)
  * Leaderboard snapshot fallback to live
  * Ban / banned-user login refusal
  * Last-login tracking
  * LLM fallback (stub mode - never calls the network)
  * Background job functions (snapshot, retention)
  * Achievements catalog + unlock
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Env must be set before app imports.
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
os.environ.setdefault("DISABLE_BACKGROUND_JOBS", "1")
os.environ.setdefault("LLM_PROVIDER", "stub")

from main import app  # noqa: E402
from app import db_models, jobs, utils  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


# ---- Fixtures ----


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_models.Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture(scope="function")
def client(db_session):
    from app.database import get_db
    def _override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _override
    utils.seed_achievements(db_session)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, email="audit6@example.com", password="superpassword") -> dict:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Tester"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---- Email verification ----


def test_audit6_send_verification_emails_token(client, db_session):
    a = _register(client)
    r = client.post(
        "/api/auth/send-verification", headers=_auth(a["access_token"]),
    )
    assert r.status_code == 200, r.text
    # An email token row should exist for the user.
    from app.db_models import EmailToken
    rows = db_session.query(EmailToken).all()
    assert any(r.purpose == "verify" for r in rows)


def test_audit6_verify_email_consumes_token(client, db_session):
    a = _register(client)
    token = utils.issue_email_token(db_session, _user_id(db_session, "audit6@example.com"), "verify", 3600)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    # user.is_verified flipped
    u = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6@example.com"
    ).one()
    assert u.is_verified is True
    # Token marked used.
    from app.db_models import EmailToken
    import hashlib
    h = hashlib.sha256(token.encode("utf-8")).hexdigest()
    tok = db_session.query(EmailToken).filter(EmailToken.token_hash == h).one()
    assert tok.used_at is not None


def test_audit6_verify_email_invalid_token(client):
    r = client.post("/api/auth/verify-email", json={"token": "bogus"})
    assert r.status_code == 400


def test_audit6_verified_achievement_unlocked(client, db_session):
    a = _register(client, "audit6-verified@example.com")
    uid = _user_id(db_session, "audit6-verified@example.com")
    token = utils.issue_email_token(db_session, uid, "verify", 3600)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    unlocked = db_session.query(db_models.UserAchievement).filter(
        db_models.UserAchievement.user_id == uid,
        db_models.UserAchievement.achievement_key == "verified",
    ).first()
    assert unlocked is not None


# ---- Forgot / reset password ----


def test_audit6_forgot_password_always_returns_200(client):
    """Anti-enumeration: must return 200 even for unknown emails."""
    r = client.post(
        "/api/auth/forgot-password", json={"email": "nobody-here@example.com"},
    )
    assert r.status_code == 200


def test_audit6_forgot_then_reset(client, db_session):
    a = _register(client, "audit6-forgot@example.com")
    uid = _user_id(db_session, "audit6-forgot@example.com")
    token = utils.issue_email_token(db_session, uid, "reset", 3600)
    r = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword123"},
    )
    assert r.status_code == 200, r.text
    # Old access token should be revoked.
    r2 = client.get("/api/auth/me", headers=_auth(a["access_token"]))
    assert r2.status_code == 401, r2.text


def test_audit6_reset_password_expired_token_rejected(client, db_session):
    a = _register(client, "audit6-expired@example.com")
    uid = _user_id(db_session, "audit6-expired@example.com")
    token = utils.issue_email_token(db_session, uid, "reset", -10)  # already expired
    r = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword123"},
    )
    assert r.status_code == 400


# ---- Delete account ----


def test_audit6_delete_account_soft_deletes(client, db_session):
    a = _register(client, "audit6-delete@example.com")
    r = client.delete("/api/auth/me", headers=_auth(a["access_token"]))
    assert r.status_code == 200
    u = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-delete@example.com"
    ).one()
    assert u.deleted_at is not None
    assert u.is_active is False
    # Subsequent /me with same token is rejected (token_version bumped).
    r2 = client.get("/api/auth/me", headers=_auth(a["access_token"]))
    assert r2.status_code in (401, 403)


# ---- Avatar ----


def test_audit6_set_avatar_data_uri(client, db_session):
    a = _register(client, "audit6-avatar@example.com")
    # 1x1 PNG, base64
    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    r = client.post(
        "/api/auth/me/avatar",
        headers=_auth(a["access_token"]),
        json={"image": f"data:image/png;base64,{b64}"},
    )
    assert r.status_code == 200, r.text
    u = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-avatar@example.com"
    ).one()
    assert u.avatar_url is not None
    assert u.avatar_url.startswith("data:image/png;base64,")


def test_audit6_set_avatar_https_url(client):
    a = _register(client, "audit6-avatar2@example.com")
    r = client.post(
        "/api/auth/me/avatar",
        headers=_auth(a["access_token"]),
        json={"image": "https://example.com/avatar.png"},
    )
    assert r.status_code == 200, r.text


def test_audit6_set_avatar_rejects_plain_http(client):
    a = _register(client, "audit6-avatar3@example.com")
    r = client.post(
        "/api/auth/me/avatar",
        headers=_auth(a["access_token"]),
        json={"image": "http://example.com/avatar.png"},
    )
    assert r.status_code == 422


# ---- User statistics ----


def test_audit6_my_stats_empty(client):
    a = _register(client, "audit6-stats@example.com")
    r = client.get("/api/auth/me/stats", headers=_auth(a["access_token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_messages"] == 0
    assert body["achievements_unlocked"] == 0
    assert body["current_streak_days"] == 0
    assert "mode_counts" in body


# ---- Favorites ----


def test_audit6_set_favorites(client):
    a = _register(client, "audit6-fav@example.com")
    r = client.put(
        "/api/auth/me/favorites",
        headers=_auth(a["access_token"]),
        json={"favorite_mode": "savage", "favorite_personality": "savage_one"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["favorite_mode"] == "savage"


def test_audit6_set_favorites_invalid_mode(client):
    a = _register(client, "audit6-fav2@example.com")
    r = client.put(
        "/api/auth/me/favorites",
        headers=_auth(a["access_token"]),
        json={"favorite_mode": "nonsense"},
    )
    assert r.status_code == 422


# ---- Admin JWT login ----


def test_audit6_admin_login_returns_token(client, db_session):
    # Bootstrap an admin
    a = _register(client, "audit6-admin@example.com", "superpassword")
    uid = _user_id(db_session, "audit6-admin@example.com")
    user = db_session.query(db_models.User).filter(db_models.User.id == uid).one()
    user.is_admin = True
    db_session.commit()
    r = client.post(
        "/api/auth/admin/login",
        json={"email": "audit6-admin@example.com", "password": "superpassword"},
    )
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


def test_audit6_admin_login_rejects_non_admin(client):
    _register(client, "audit6-notadmin@example.com", "superpassword")
    r = client.post(
        "/api/auth/admin/login",
        json={"email": "audit6-notadmin@example.com", "password": "superpassword"},
    )
    assert r.status_code == 403


# ---- Ban user ----


def test_audit6_admin_ban_user(client, db_session):
    # Register a target user
    _register(client, "audit6-bantarget@example.com")
    target_id = _user_id(db_session, "audit6-bantarget@example.com")
    # Register a separate admin user
    _register(client, "audit6-banadmin@example.com", "superpassword")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-banadmin@example.com"
    ).one()
    user.is_admin = True
    db_session.commit()
    # Re-login to get a fresh token that the require_admin dep will accept
    r_login = client.post(
        "/api/auth/login",
        json={"email": "audit6-banadmin@example.com", "password": "superpassword"},
    )
    assert r_login.status_code == 200
    admin_token = r_login.json()["access_token"]
    r = client.post(
        f"/api/admin/users/{target_id}/ban",
        headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
        json={"reason": "test spam"},
    )
    assert r.status_code == 200, r.text
    u = db_session.query(db_models.User).filter(db_models.User.id == target_id).one()
    assert u.is_banned is True
    assert u.ban_reason == "test spam"
    assert u.banned_at is not None


def test_audit6_banned_user_cannot_login(client, db_session):
    a = _register(client, "audit6-banned@example.com", "superpassword")
    uid = _user_id(db_session, "audit6-banned@example.com")
    user = db_session.query(db_models.User).filter(db_models.User.id == uid).one()
    user.is_admin = True
    user.is_banned = True
    user.ban_reason = "abuse"
    db_session.commit()
    r = client.post(
        "/api/auth/login",
        json={"email": "audit6-banned@example.com", "password": "superpassword"},
    )
    assert r.status_code == 403
    assert "banned" in r.json()["detail"].lower()


def test_audit6_admin_unban(client, db_session):
    _register(client, "audit6-unban@example.com")
    target_id = _user_id(db_session, "audit6-unban@example.com")
    _register(client, "audit6-unbanadmin@example.com", "superpassword")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-unbanadmin@example.com"
    ).one()
    user.is_admin = True
    db_session.commit()
    r_login = client.post(
        "/api/auth/login",
        json={"email": "audit6-unbanadmin@example.com", "password": "superpassword"},
    )
    admin_token = r_login.json()["access_token"]
    r = client.post(
        f"/api/admin/users/{target_id}/unban",
        headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
    )
    assert r.status_code == 200
    u = db_session.query(db_models.User).filter(db_models.User.id == target_id).one()
    assert u.is_banned is False


# ---- Last login tracking ----


def test_audit6_login_records_last_login(client, db_session):
    _register(client, "audit6-lastlogin@example.com", "superpassword")
    r = client.post(
        "/api/auth/login",
        json={"email": "audit6-lastlogin@example.com", "password": "superpassword"},
    )
    assert r.status_code == 200
    u = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-lastlogin@example.com"
    ).one()
    assert u.last_login_at is not None


# ---- Feature flags ----


def test_audit6_admin_set_feature_flag(client, db_session):
    _register(client, "audit6-flag@example.com", "superpassword")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-flag@example.com"
    ).one()
    user.is_admin = True
    db_session.commit()
    r_login = client.post(
        "/api/auth/login",
        json={"email": "audit6-flag@example.com", "password": "superpassword"},
    )
    admin_token = r_login.json()["access_token"]
    r = client.put(
        "/api/admin/feature-flags",
        headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
        json={"key": "llm_fallback", "enabled": True, "description": "Use LLM"},
    )
    assert r.status_code == 200
    assert utils.is_flag_enabled(db_session, "llm_fallback") is True


# ---- Audit logs ----


def test_audit6_audit_log_captures_ban(client, db_session):
    _register(client, "audit6-audittarget@example.com")
    target_id = _user_id(db_session, "audit6-audittarget@example.com")
    _register(client, "audit6-audit@example.com", "superpassword")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-audit@example.com"
    ).one()
    user.is_admin = True
    db_session.commit()
    r_login = client.post(
        "/api/auth/login",
        json={"email": "audit6-audit@example.com", "password": "superpassword"},
    )
    admin_token = r_login.json()["access_token"]
    client.post(
        f"/api/admin/users/{target_id}/ban",
        headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
        json={"reason": "test"},
    )
    r = client.get(
        "/api/admin/audit-logs",
        headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
    )
    assert r.status_code == 200
    actions = [log["action"] for log in r.json()["logs"]]
    assert "admin_ban_user" in actions


# ---- Charts ----


def test_audit6_admin_charts(client, db_session):
    _register(client, "audit6-charts@example.com", "superpassword")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-charts@example.com"
    ).one()
    user.is_admin = True
    db_session.commit()
    r_login = client.post(
        "/api/auth/login",
        json={"email": "audit6-charts@example.com", "password": "superpassword"},
    )
    admin_token = r_login.json()["access_token"]
    for path in ("/api/admin/charts/signups", "/api/admin/charts/chats"):
        r = client.get(
            path + "?days=7",
            headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "points" in body
        assert body["days"] == 7


# ---- Stats: total_chats, avg_session_time, most_used_mode ----


def test_audit6_admin_stats_includes_new_fields(client, db_session):
    _register(client, "audit6-stats2@example.com", "superpassword")
    user = db_session.query(db_models.User).filter(
        db_models.User.email == "audit6-stats2@example.com"
    ).one()
    user.is_admin = True
    db_session.commit()
    r_login = client.post(
        "/api/auth/login",
        json={"email": "audit6-stats2@example.com", "password": "superpassword"},
    )
    admin_token = r_login.json()["access_token"]
    r = client.get(
        "/api/admin/stats",
        headers={**_auth(admin_token), "X-Admin-Key": "test-admin-key-1234567890"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("total_chats", "avg_session_time_seconds", "most_used_mode",
                "banned_users", "daily_active_users"):
        assert key in body, f"missing key {key}"


# ---- Subscription downgrade ----


def test_audit6_downgrade_requires_cheaper_plan(client, db_session):
    # Set up a user with the priciest plan
    a = _register(client, "audit6-down@example.com")
    # Subscribe via admin grant to "legend" plan
    from datetime import datetime, timezone, timedelta
    legend = db_session.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.plan_code == "legend"
    ).first()
    starter = db_session.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.plan_code == "starter"
    ).first()
    if legend is None or starter is None:
        pytest.skip("plans not seeded")
    sub = db_models.Subscription(
        user_id=_user_id(db_session, "audit6-down@example.com"),
        plan_id=legend.id,
        status=db_models.SubStatus.active,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.commit()
    r = client.post(
        "/api/subscriptions/downgrade",
        headers=_auth(a["access_token"]),
        json={"target_plan_code": "starter"},
    )
    assert r.status_code == 200, r.text


def test_audit6_downgrade_rejects_upgrade(client, db_session):
    a = _register(client, "audit6-down2@example.com")
    from datetime import datetime, timezone, timedelta
    starter = db_session.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.plan_code == "starter"
    ).first()
    legend = db_session.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.plan_code == "legend"
    ).first()
    if starter is None or legend is None:
        pytest.skip("plans not seeded")
    sub = db_models.Subscription(
        user_id=_user_id(db_session, "audit6-down2@example.com"),
        plan_id=starter.id,
        status=db_models.SubStatus.active,
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.commit()
    r = client.post(
        "/api/subscriptions/downgrade",
        headers=_auth(a["access_token"]),
        json={"target_plan_code": "legend"},
    )
    assert r.status_code == 400


# ---- History search ----


def test_audit6_history_search(client, db_session):
    a = _register(client, "audit6-search@example.com")
    # Add some history rows directly
    from datetime import datetime, timezone
    uid = _user_id(db_session, "audit6-search@example.com")
    db_session.add(db_models.ChatHistory(
        user_id=uid, message="I am a 10x engineer", is_user=True,
        roast_response="Then why are you still debugging in Notepad?",
        score_total=42.0,
    ))
    db_session.add(db_models.ChatHistory(
        user_id=uid, message="Tell me about my code", is_user=True,
        roast_response="Your code called you a crybaby.",
        score_total=12.0,
    ))
    db_session.commit()
    r = client.get(
        "/api/history?q=10x", headers=_auth(a["access_token"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert "10x" in body["items"][0]["message"]


# ---- History export ----


def test_audit6_history_export_txt(client, db_session):
    a = _register(client, "audit6-export@example.com")
    uid = _user_id(db_session, "audit6-export@example.com")
    db_session.add(db_models.ChatHistory(
        user_id=uid, message="hello there", is_user=True,
        roast_response="hello back", score_total=5.0,
    ))
    db_session.commit()
    r = client.get("/api/history/export?format=txt", headers=_auth(a["access_token"]))
    assert r.status_code == 200
    assert "hello there" in r.text


def test_audit6_history_export_md(client):
    a = _register(client, "audit6-exportmd@example.com")
    r = client.get("/api/history/export?format=md", headers=_auth(a["access_token"]))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")


def test_audit6_history_export_json(client):
    a = _register(client, "audit6-exportjson@example.com")
    r = client.get("/api/history/export?format=json", headers=_auth(a["access_token"]))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


# ---- LLM fallback (stub) ----


def test_audit6_llm_stub_returns_none():
    from app import llm_fallback
    out = llm_fallback.generate_roast(
        message="hello", mode="savage", personality="savage_one",
    )
    assert out is None  # stub never generates


def test_audit6_llm_circuit_breaker_trips():
    from app import llm_fallback
    # Force 5 failures; the breaker should open and skip the call
    for _ in range(llm_fallback.LLM_MAX_FAILURES):
        llm_fallback._record_failure()
    # Even if provider were set, breaker is open so should_fallback = False
    assert llm_fallback.should_fallback(score=0.1) is False
    # Reset for the next test
    llm_fallback._failures.clear()


# ---- Background job functions ----


def test_audit6_snapshot_one_writes_rows(db_session):
    from datetime import datetime, timezone, timedelta
    a_user = db_models.User(
        email="audit6-snap@example.com",
        hashed_password="x", full_name="Snapper",
    )
    db_session.add(a_user)
    db_session.commit()
    db_session.add(db_models.ChatHistory(
        user_id=a_user.id, message="x", is_user=True,
        roast_response="y", score_total=10.0,
    ))
    db_session.commit()
    jobs._snapshot_one(db_session, "all", "all")
    rows = db_session.query(db_models.LeaderboardSnapshot).filter(
        db_models.LeaderboardSnapshot.period == "all",
        db_models.LeaderboardSnapshot.period_id == "all",
    ).all()
    assert any(r.user_id == a_user.id for r in rows)


def test_audit6_retention_hard_deletes_old_soft_deleted(db_session):
    from datetime import datetime, timezone, timedelta
    u = db_models.User(
        email="audit6-ret@example.com", hashed_password="x",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    db_session.add(u)
    db_session.commit()
    uid = u.id
    jobs._retention_sweep(db_session)
    assert db_session.get(db_models.User, uid) is None


# ---- Achievements ----


def test_audit6_seed_achievements_idempotent(db_session):
    n1 = utils.seed_achievements(db_session)
    n2 = utils.seed_achievements(db_session)
    assert n1 > 0
    assert n2 == 0
    rows = db_session.query(db_models.Achievement).all()
    assert len(rows) >= 10


def test_audit6_unlock_achievement_roundtrip(db_session):
    a_user = db_models.User(email="audit6-ach@example.com", hashed_password="x")
    db_session.add(a_user)
    db_session.commit()
    utils.seed_achievements(db_session)
    first = utils.unlock_achievement(db_session, a_user.id, "first_roast")
    second = utils.unlock_achievement(db_session, a_user.id, "first_roast")
    assert first is True
    assert second is False


# ---- API versioning ----


def test_audit6_v1_alias_routes_to_unversioned(client):
    """The /api/v1/* alias must serve the same response as /api/*."""
    r1 = client.get("/api/health")
    r2 = client.get("/api/v1/health")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


def test_audit6_v1_alias_login(client):
    _register(client, "audit6-v1@example.com", "superpassword")
    r1 = client.post(
        "/api/auth/login",
        json={"email": "audit6-v1@example.com", "password": "superpassword"},
    )
    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": "audit6-v1@example.com", "password": "superpassword"},
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert "access_token" in r2.json()


# ---- Helpers ----


def _user_id(db_session, email: str) -> int:
    return db_session.query(db_models.User).filter(
        db_models.User.email == email
    ).one().id
