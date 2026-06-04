"""Tests for the authentication, payment, and subscription system."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Disable rate limiting + use SQLite for tests
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-minimum-1234")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db_models
from app.database import Base, get_db
from app.library import LIB
from main import app


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    """Library is required for /api/session/start to return anything other than 503."""
    LIB.load()


# ---- Test DB setup (use a fresh in-memory DB per test) ----
@pytest.fixture(scope="function")
def test_engine():
    # Use StaticPool so a single in-memory SQLite connection is shared across threads.
    # The DB is created fresh for each test (scope=function).
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_engine):
    """A TestClient backed by our test database."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---- Helpers ----
def _register_user(client, email="test@example.com", password="TestPass123!", name="Test User"):
    return client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": name,
        "gender_preference": "neutral",
    })


def _login(client, email="test@example.com", password="TestPass123!"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---- Registration tests ----
def test_register_new_user(client):
    r = _register_user(client, "alice@example.com", "StrongPass123", "Alice")
    assert r.status_code == 201
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_register_duplicate_email(client):
    # First registration should succeed
    r1 = _register_user(client, "dup@example.com")
    assert r1.status_code == 201
    # Second registration with same email should fail with 409
    r2 = _register_user(client, "dup@example.com")
    assert r2.status_code == 409


def test_register_password_too_short(client):
    r = client.post("/api/auth/register", json={
        "email": "shortpw@example.com",
        "password": "123",
    })
    assert r.status_code == 422  # Pydantic validation error


def test_register_invalid_email(client):
    r = client.post("/api/auth/register", json={
        "email": "not-an-email",
        "password": "GoodPass123",
    })
    assert r.status_code == 422


# ---- Login tests ----
def test_login_success(client):
    _register_user(client, "bob@example.com", "BobPass123")
    r = _login(client, "bob@example.com", "BobPass123")
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_wrong_password(client):
    _register_user(client, "carol@example.com", "CarolPass123")
    r = client.post("/api/auth/login", json={
        "email": "carol@example.com", "password": "WRONG"
    })
    assert r.status_code == 401


def test_login_nonexistent_user(client):
    r = client.post("/api/auth/login", json={
        "email": "nobody@example.com", "password": "AnyPass123"
    })
    assert r.status_code == 401


# ---- /me endpoint ----
def test_get_me_requires_auth(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_get_me_with_token(client):
    _register_user(client, "dave@example.com", "DavePass123", "Dave User")
    token = _login(client, "dave@example.com", "DavePass123").json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "dave@example.com"
    assert body["full_name"] == "Dave User"  # explicit name passed to helper
    assert body["is_admin"] is False
    assert body["has_active_subscription"] is False


def test_update_me(client):
    _register_user(client, "eve@example.com", "EvePass123")
    token = _login(client, "eve@example.com", "EvePass123").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.patch("/api/auth/me", json={"full_name": "Eve Updated", "gender_preference": "female"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Eve Updated"
    assert body["gender_preference"] == "female"


# ---- Token refresh ----
def test_refresh_token(client):
    _register_user(client, "frank@example.com", "FrankPass123")
    login = _login(client, "frank@example.com", "FrankPass123")
    refresh = login.json()["refresh_token"]
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_refresh_with_access_token_rejected(client):
    _register_user(client, "grace@example.com", "GracePass123")
    access = _login(client, "grace@example.com", "GracePass123").json()["access_token"]
    r = client.post("/api/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


# ---- Subscription plans ----
def test_list_plans(client):
    r = client.get("/api/payments/plans")
    assert r.status_code == 200
    body = r.json()
    assert "plans" in body
    plan_codes = {p["plan_code"] for p in body["plans"]}
    assert "starter" in plan_codes
    assert "pro" in plan_codes
    assert "legend" in plan_codes


def test_list_plans_starter_price(client):
    r = client.get("/api/payments/plans")
    plans = r.json()["plans"]
    starter = next(p for p in plans if p["plan_code"] == "starter")
    assert starter["price_paise"] == 29900  # ₹299


# ---- Admin endpoints require auth ----
def test_admin_users_requires_auth(client):
    r = client.get("/api/admin/users")
    assert r.status_code == 401


def test_admin_users_requires_admin(client):
    _register_user(client, "henry@example.com", "HenryPass123")
    token = _login(client, "henry@example.com", "HenryPass123").json()["access_token"]
    r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403  # Not admin


# ---- History endpoints require auth ----
def test_history_requires_auth(client):
    r = client.get("/api/history")
    assert r.status_code == 401


# ---- Change password ----
def test_change_password(client):
    _register_user(client, "iris@example.com", "IrisPass123")
    token = _login(client, "iris@example.com", "IrisPass123").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/auth/change-password", json={
        "current_password": "IrisPass123", "new_password": "NewIrisPass456"
    }, headers=headers)
    assert r.status_code == 200
    # Login with old password should now fail
    r = _login(client, "iris@example.com", "IrisPass123")
    assert r.status_code == 401
    # Login with new password should succeed
    r = _login(client, "iris@example.com", "NewIrisPass456")
    assert r.status_code == 200


# ---- Public leaderboard ----

def test_public_leaderboard_no_auth_required(client):
    """Leaderboard is public - no Authorization header needed."""
    r = client.get("/api/leaderboard?period=week")
    assert r.status_code == 200
    body = r.json()
    assert "period" in body
    assert "entries" in body
    assert isinstance(body["entries"], list)


def test_public_leaderboard_periods(client):
    """week / month / all should all be accepted."""
    for p in ("week", "month", "all"):
        r = client.get(f"/api/leaderboard?period={p}&limit=5")
        assert r.status_code == 200
        assert r.json()["period"] != ""


def test_public_leaderboard_rejects_bad_period(client):
    r = client.get("/api/leaderboard?period=garbage")
    assert r.status_code == 422


def test_public_leaderboard_masks_email(client):
    """Email should never be returned in clear, only the masked prefix@domain form."""
    # Register a user and inject a chat history row
    _register_user(client, "leader@example.com", "LeaderPass123")
    token = _login(client, "leader@example.com", "LeaderPass123").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Start + roast to seed chat history
    sid = client.post("/api/session/start", json={"mode": "savage", "personality": "savage_one"}, headers=headers).json()["session_id"]
    client.post(f"/api/session/{sid}/roast", json={"message": "hi"}, headers=headers)
    # Query leaderboard
    r = client.get("/api/leaderboard?period=all")
    assert r.status_code == 200
    entries = r.json()["entries"]
    # Our user must be in the top N
    found = any(e.get("masked_email") for e in entries)
    assert found, "no entries with masked_email returned"
    for e in entries:
        if e.get("masked_email"):
            assert "leader@example.com" not in e["masked_email"], "raw email leaked"
            assert "@" in e["masked_email"]
