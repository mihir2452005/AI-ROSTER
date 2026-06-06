"""Shared pytest fixtures and environment setup for all tests.

Centralising env-var setup here means individual test files don't have to
remember to set the same secrets, and the prod secret validation in
app.auth.validate_secrets() can never crash a test run.
"""
from __future__ import annotations

import os

# These MUST be set before any backend.app import so the modules that read
# env vars at import time (e.g. main.py) see them.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "1")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-1234567890")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-minimum-1234")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW", "1")
# Loosen the per-endpoint overrides too so tests don't 429.
os.environ.setdefault("RATE_LIMIT_REGISTER", "10000")
os.environ.setdefault("RATE_LIMIT_LOGIN", "10000")
os.environ.setdefault("RATE_LIMIT_REFRESH", "10000")
os.environ.setdefault("RATE_LIMIT_SESSION_START", "10000")
os.environ.setdefault("RATE_LIMIT_ADMIN_CLEANUP", "10000")
# Don't spin up the background scheduler in tests — it would
# keep the pytest process alive past the last test.
os.environ.setdefault("DISABLE_BACKGROUND_JOBS", "1")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_xxxxxxxxxxxx")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "test_secret_xxxxxxxxxxxxxx")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_xxxxxxxxx")

import sys
from pathlib import Path

# Make the backend package importable when running `pytest` from the
# backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db_models  # noqa: E402  (env vars must be set first)
from app.database import Base, get_db  # noqa: E402


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session, one per test, with a fresh schema.

    StaticPool is required so all connections share the same in-memory DB
    even when FastAPI's threadpool opens more than one connection.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with the in-memory DB injected.

    Tests can use this fixture directly. The library is auto-loaded by the
    per-test autouse fixture in each test file (kept there so the loader
    behaviour stays explicit per module).
    """
    from fastapi.testclient import TestClient
    from main import app

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    # Clear the in-memory rate-limit and feature-flag cache between tests
    # so test order doesn't leak into the global sliding-window buckets.
    from app import cache, utils
    try:
        cache.clear_all()
    except Exception:
        pass
    try:
        utils._feature_flags.clear()
        utils._feature_flag_expiry.clear()
    except Exception:
        pass
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
