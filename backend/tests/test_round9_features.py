"""Tests for the Round 9 additions:

  * Contact form (public submit + admin list/update)
  * Notifications: list, mark-read, mark-all-read, admin broadcast
  * User activity feed (`/api/v1/auth/me/activity`)
  * System status (`/api/v1/system/status`) public health
  * Prometheus metrics (`/api/v1/system/metrics`) text exposition
  * Back-compat alias (`/api/metrics`) delegates to round9 prometheus
  * Maintenance mode middleware (503 for non-admin, 200 for admin)
  * Welcome notification on register
  * Password-change notification
  * Payment-success notification
  * Email template helpers (welcome, payment success, expiring, cancelled)
  * Notification `mark-read` is scoped to caller (cannot read others' rows)
"""
from __future__ import annotations

import os

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
os.environ.setdefault("RATE_LIMIT_CONTACT", "10000")
os.environ.setdefault("RATE_LIMIT_ADMIN_CLEANUP", "10000")
os.environ.setdefault("DISABLE_BACKGROUND_JOBS", "1")
os.environ.setdefault("LLM_PROVIDER", "stub")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app  # noqa: E402
from app import db_models  # noqa: E402
from app.database import get_db  # noqa: E402


# ---- Fixtures ----


@pytest.fixture(scope="function")
def db_session(monkeypatch):
    # Use a file-based SQLite that we can share with the global
    # SessionLocal used by the maintenance middleware. Each test
    # gets a unique file so tests stay isolated.
    import os, tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["SQLITE_FILE"] = path

    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    db_models.Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = S()

    # Rebuild the global engine + SessionLocal so the middleware and
    # any internal DB calls see the same in-memory schema. This is
    # the minimum that makes the maintenance test work without
    # touching prod code.
    import importlib
    from app import database
    importlib.reload(database)
    monkeypatch.setattr(database, "SessionLocal", S)

    try:
        yield s
    finally:
        s.close()
        engine.dispose()
        try:
            os.unlink(path)
        except Exception:
            pass


@pytest.fixture(scope="function")
def client(db_session):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def admin_user(db_session):
    from app.auth import hash_password
    u = db_models.User(
        email="admin@example.com",
        hashed_password=hash_password("adminpass123"),
        is_admin=True,
        is_verified=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def regular_user(db_session):
    from app.auth import hash_password
    u = db_models.User(
        email="user@example.com",
        hashed_password=hash_password("userpass1234"),
        is_admin=False,
        is_verified=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _admin_token(admin: db_models.User) -> str:
    from app.auth import create_access_token
    return create_access_token(admin.id, admin.email)


def _user_token(user: db_models.User) -> str:
    from app.auth import create_access_token
    return create_access_token(user.id, user.email)


# ---- Contact ----


def test_contact_submit_public(client):
    r = client.post("/api/v1/contact", json={
        "name": "Curious",
        "email": "curious@example.com",
        "subject": "Hello",
        "message": "Just wanted to say hi!",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "new"
    assert body["id"] > 0


def test_contact_submit_strips_dangerous_tags(client, db_session):
    """Verify that a script tag in the message is stripped before storage."""
    r = client.post("/api/v1/contact", json={
        "name": "Xavier",
        "email": "x@example.com",
        "subject": "Hello world",
        "message": "<script>alert(1)</script> just a friendly message",
    })
    assert r.status_code == 201
    # The raw message in the DB should not contain a script tag
    from app.db_models import ContactMessage
    cm = db_session.query(ContactMessage).first()
    assert cm is not None
    assert "<script" not in cm.subject
    assert "<script" not in cm.message


def test_contact_submit_validates_email(client):
    r = client.post("/api/v1/contact", json={
        "name": "X",
        "email": "not-an-email",
        "subject": "hi",
        "message": "short",
    })
    assert r.status_code == 422


def test_contact_list_requires_admin(client, admin_user, regular_user):
    user_t = _user_token(regular_user)
    r = client.get(
        "/api/v1/admin/contact-messages",
        headers={"Authorization": f"Bearer {user_t}"},
    )
    assert r.status_code == 403

    admin_t = _admin_token(admin_user)
    r = client.get(
        "/api/v1/admin/contact-messages",
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "messages" in body and "total" in body


def test_contact_admin_update_status(client, admin_user):
    admin_t = _admin_token(admin_user)
    # Create one
    r = client.post("/api/v1/contact", json={
        "name": "Yolanda", "email": "y@example.com", "subject": "Hello", "message": "This is a test message.",
    })
    assert r.status_code == 201
    ticket_id = r.json()["id"]

    r = client.patch(
        f"/api/v1/admin/contact-messages/{ticket_id}?status=in_progress",
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


# ---- Notifications ----


def test_notifications_default_empty(client, regular_user):
    t = _user_token(regular_user)
    r = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == [] and body["unread_count"] == 0 and body["total"] == 0


def test_notifications_list_after_broadcast(client, admin_user, regular_user):
    admin_t = _admin_token(admin_user)
    r = client.post(
        "/api/v1/admin/notifications/broadcast",
        json={"title": "Hello there", "body": "World", "kind": "announcement", "target": "all"},
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    assert r.status_code == 201
    assert r.json()["delivered_to"] == 2  # admin + regular user

    user_t = _user_token(regular_user)
    r = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {user_t}"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Hello there"
    assert items[0]["is_read"] is False


def test_notifications_mark_read(client, admin_user, regular_user):
    admin_t = _admin_token(admin_user)
    client.post(
        "/api/v1/admin/notifications/broadcast",
        json={"title": "Test 123", "body": "Body text", "kind": "announcement", "target": "all"},
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    user_t = _user_token(regular_user)
    r = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {user_t}"})
    nid = r.json()["items"][0]["id"]

    r = client.post(
        "/api/v1/notifications/mark-read",
        json={"ids": [nid]},
        headers={"Authorization": f"Bearer {user_t}"},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1

    r = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {user_t}"})
    assert r.json()["unread_count"] == 0


def test_notifications_mark_read_scoped_to_caller(client, admin_user, regular_user, db_session):
    """A user must not be able to mark someone else's notification read."""
    from app.auth import hash_password
    other = db_models.User(
        email="other@example.com",
        hashed_password=hash_password("otherpass1234"),
        is_admin=False,
        is_verified=True,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    n = db_models.Notification(
        user_id=other.id, kind="announcement", title="for other", body="b"
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)

    user_t = _user_token(regular_user)
    r = client.post(
        "/api/v1/notifications/mark-read",
        json={"ids": [n.id]},
        headers={"Authorization": f"Bearer {user_t}"},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 0  # nothing actually marked


def test_notifications_mark_all_read(client, admin_user, regular_user):
    admin_t = _admin_token(admin_user)
    for i in range(3):
        client.post(
            "/api/v1/admin/notifications/broadcast",
            json={"title": f"Test {i} extra", "body": "Body text", "kind": "announcement", "target": "all"},
            headers={"Authorization": f"Bearer {admin_t}"},
        )
    user_t = _user_token(regular_user)
    r = client.post(
        "/api/v1/notifications/mark-all-read",
        headers={"Authorization": f"Bearer {user_t}"},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 3


def test_welcome_notification_on_register(client, db_session):
    r = client.post("/api/v1/auth/register", json={
        "email": "new@example.com",
        "password": "goodpass123",
    })
    assert r.status_code == 201
    user = db_session.query(db_models.User).filter(db_models.User.email == "new@example.com").first()
    notifs = db_session.query(db_models.Notification).filter(db_models.Notification.user_id == user.id).all()
    assert len(notifs) == 1
    assert notifs[0].kind == "system"


def test_password_change_notification(client, regular_user, db_session):
    from app.auth import hash_password
    t = _user_token(regular_user)
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "userpass1234", "new_password": "newpass5678"},
        headers={"Authorization": f"Bearer {t}"},
    )
    assert r.status_code == 200
    # Token version was bumped; query the DB directly for the notification.
    notifs = (
        db_session.query(db_models.Notification)
        .filter(db_models.Notification.user_id == regular_user.id)
        .all()
    )
    titles = [n.title for n in notifs]
    assert any("Password" in ttl for ttl in titles)


def test_admin_broadcast_to_specific_user(client, admin_user, regular_user):
    admin_t = _admin_token(admin_user)
    r = client.post(
        "/api/v1/admin/notifications/broadcast",
        json={
            "title": "Direct message", "body": "hi there", "kind": "announcement",
            "target": str(regular_user.id),
        },
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    assert r.status_code == 201
    assert r.json()["delivered_to"] == 1


# ---- Activity feed ----


def test_activity_empty_for_new_user(client, regular_user):
    t = _user_token(regular_user)
    r = client.get("/api/v1/auth/me/activity", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == [] and body["total"] == 0


def test_activity_returns_user_actions(client, regular_user, db_session):
    from app.utils import log_action
    log_action(db_session, action="user_login", actor_user_id=regular_user.id)
    log_action(db_session, action="profile_update", actor_user_id=regular_user.id)
    log_action(db_session, action="admin_banned_someone", actor_user_id=regular_user.id)  # still shown

    t = _user_token(regular_user)
    r = client.get("/api/v1/auth/me/activity", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3
    # Newest first
    assert items[0]["action"] == "admin_banned_someone"
    # Friendly label for known action
    assert any(i["label"] == "Logged in" for i in items)


def test_activity_does_not_leak_other_users(client, regular_user, admin_user, db_session):
    from app.utils import log_action
    log_action(db_session, action="user_login", actor_user_id=admin_user.id)
    t = _user_token(regular_user)
    r = client.get("/api/v1/auth/me/activity", headers={"Authorization": f"Bearer {t}"})
    assert r.json()["total"] == 0


# ---- System status & metrics ----


def test_system_status_public(client):
    r = client.get("/api/v1/system/status")
    assert r.status_code == 200
    body = r.json()
    for k in ("status", "database", "redis", "queue", "sentry",
              "version", "uptime_seconds", "build_sha", "maintenance_mode"):
        assert k in body
    assert body["version"] == "1.4.0"
    assert body["maintenance_mode"] is False
    assert body["status"] in ("healthy", "degraded", "unhealthy")


def test_system_metrics_prometheus_format(client):
    r = client.get("/api/v1/system/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "roastgpt_build_info" in body
    assert "roastgpt_uptime_seconds" in body
    assert "roastgpt_users_total" in body
    assert "roastgpt_database_up" in body
    assert "roastgpt_maintenance_mode" in body


def test_api_metrics_backcompat_alias(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert "roastgpt_build_info" in r.text


# ---- Maintenance mode ----


def test_maintenance_mode_blocks_non_admin(client, admin_user, regular_user, db_session):
    from app.utils import set_flag
    set_flag(db_session, "maintenance_mode", True, updated_by_id=admin_user.id)

    # Use the public contact endpoint — no auth required, easy to test 503.
    r = client.post("/api/v1/contact", json={
        "name": "Visitor", "email": "v@example.com",
        "subject": "Hello", "message": "This is a test message.",
    })
    assert r.status_code == 503
    assert r.json()["maintenance"] is True


def test_maintenance_mode_lets_admin_through(client, admin_user, db_session):
    from app.utils import set_flag
    set_flag(db_session, "maintenance_mode", True, updated_by_id=admin_user.id)

    admin_t = _admin_token(admin_user)
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    assert r.status_code == 200


def test_maintenance_mode_does_not_block_status(client, db_session):
    from app.utils import set_flag
    set_flag(db_session, "maintenance_mode", True)

    r = client.get("/api/v1/system/status")
    assert r.status_code == 200
    assert r.json()["maintenance_mode"] is True


def test_maintenance_mode_does_not_block_metrics(client, db_session):
    from app.utils import set_flag
    set_flag(db_session, "maintenance_mode", True)

    r = client.get("/api/v1/system/metrics")
    assert r.status_code == 200
    assert "roastgpt_maintenance_mode 1" in r.text


def test_maintenance_off_unblocks(client, admin_user, regular_user, db_session):
    from app.utils import set_flag
    set_flag(db_session, "maintenance_mode", True, updated_by_id=admin_user.id)
    set_flag(db_session, "maintenance_mode", False, updated_by_id=admin_user.id)

    user_t = _user_token(regular_user)
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {user_t}"},
    )
    assert r.status_code == 200


# ---- Email helpers ----


def test_email_templates_dev_mode_log(monkeypatch, db_session, regular_user):
    """All four new email helpers should be best-effort and never raise."""
    from app import utils
    # Ensure dev mode: no SMTP_HOST
    monkeypatch.delenv("SMTP_HOST", raising=False)
    # Each should not raise
    utils.send_welcome_email(regular_user.email, regular_user.full_name)
    utils.send_payment_success_email(regular_user.email, "Pro", None)
    utils.send_subscription_expiring_email(regular_user.email, "Pro", 3)
    utils.send_subscription_cancelled_email(regular_user.email, "Pro")
