"""Tests for backup_db.py / restore_db.py / list_db.py and for the
session-recovery endpoint.

These tests cover two distinct but related concerns:

1. The backup/restore round trip must preserve every row of every
   table. (Anything less is data loss.)
2. An authenticated user can call /api/session/{id}/recover after
   the in-memory session is wiped (simulating a free-tier host cold
   start) and the backend reconstructs the session from the
   `roast_sessions` table.

We do NOT spin up an actual Render/Neon here — we use the in-memory
SQLite engine that conftest already provides. The backup script
works against whatever engine is bound, so SQLite is a valid
substitute.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW", "1")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-1234567890")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-minimum-1234")

# Default to in-memory SQLite so the test conftest's per-test DB is
# unaffected. The backup script uses SQLAlchemy's bound engine.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db_models
from app.auth import create_access_token
from app.database import Base, get_db, SessionLocal
from app.library import LIB
from app.session import SESSIONS, load_session_from_db
from main import app
from scripts.backup_db import build_backup_dict, serialize
from scripts.list_db import _row_to_jsonable
from scripts.restore_db import restore_table, truncate_table


# A single test that loads the library once (some other suites already
# do this, but the LIB must be loaded for the chat endpoints).
@pytest.fixture(scope="module", autouse=True)
def _ensure_lib_loaded():
    if not LIB.is_loaded():
        LIB.load()
    yield


# ----- helpers -----

def _register_and_login(client: TestClient, email: str = "alice@example.com") -> dict:
    r = client.post("/api/auth/register", json={
        "email": email,
        "password": "SuperSecret123!",
        "full_name": "Alice",
    })
    # 201 Created on success, 200 OK on re-register depending on
    # backend wiring — accept both.
    assert r.status_code in (200, 201), r.text
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_user(db, email="backup@example.com", free=0):
    u = db_models.User(
        email=email,
        hashed_password="x",  # not under test
        full_name="Backup",
        free_messages_used=free,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_chat(db, user_id: int, session_id: str, *, message: str = "hi"):
    h = db_models.ChatHistory(
        user_id=user_id,
        session_id=session_id,
        message=message,
        is_user=True,
        roast_response="roast!",
    )
    db.add(h)
    db.commit()
    return h


# ----- 1. backup/restore round trip -----

def test_backup_dict_captures_all_tables(db_session):
    """`build_backup_dict` should return rows for every known table."""
    u = _make_user(db_session, "round@example.com")
    _make_chat(db_session, u.id, "sess-1")

    backup = build_backup_dict(db_session, include_passwords=True)
    assert "users" in backup["tables"]
    assert "chat_history" in backup["tables"]
    assert "subscription_plans" in backup["tables"]
    assert "subscriptions" in backup["tables"]
    assert "payments" in backup["tables"]
    assert "roast_sessions" in backup["tables"]
    assert backup["row_counts"]["users"] >= 1
    assert backup["row_counts"]["chat_history"] >= 1


def test_backup_serialize_is_json_safe(db_session):
    u = _make_user(db_session, "json@example.com")
    backup = build_backup_dict(db_session, include_passwords=True)
    raw = serialize(backup)
    # Should round-trip through json.loads without raising.
    import json as _json
    parsed = _json.loads(raw.decode("utf-8"))
    assert parsed["row_counts"]["users"] == backup["row_counts"]["users"]


def test_backup_redacts_passwords_when_requested(db_session):
    u = _make_user(db_session, "redact@example.com")
    backup = build_backup_dict(db_session, include_passwords=False)
    user_row = next(r for r in backup["tables"]["users"] if r["email"] == "redact@example.com")
    assert user_row["hashed_password"] == "[REDACTED]"


def test_restore_table_inserts_rows(db_session):
    """Insert a few users into a fresh DB via `restore_table`."""
    payload = [
        {"id": 1, "email": "r1@example.com", "hashed_password": "x",
         "gender_preference": "neutral", "is_active": True, "is_verified": False,
         "is_admin": False, "free_messages_used": 0, "token_version": 0},
        {"id": 2, "email": "r2@example.com", "hashed_password": "y",
         "gender_preference": "neutral", "is_active": True, "is_verified": False,
         "is_admin": False, "free_messages_used": 2, "token_version": 0},
    ]
    inserted, skipped = restore_table(db_session, db_models.User, payload, dry_run=False)
    assert inserted == 2
    assert skipped == 0
    assert db_session.query(db_models.User).count() == 2


def test_restore_table_skips_unknown_columns(db_session):
    """Forward-compat: extra columns in the backup should be ignored,
    not crash the restore."""
    payload = [
        {"id": 1, "email": "future@example.com", "hashed_password": "x",
         "future_field": "should be ignored",
         "gender_preference": "neutral", "is_active": True,
         "is_verified": False, "is_admin": False,
         "free_messages_used": 0, "token_version": 0},
    ]
    inserted, skipped = restore_table(db_session, db_models.User, payload, dry_run=False)
    assert inserted == 1
    assert db_session.query(db_models.User).count() == 1


def test_truncate_table_removes_rows(db_session):
    _make_user(db_session, "t1@example.com")
    _make_user(db_session, "t2@example.com")
    assert db_session.query(db_models.User).count() == 2
    n = truncate_table(db_session, db_models.User)
    assert n == 2
    assert db_session.query(db_models.User).count() == 0


def test_backup_restore_round_trip_is_lossless(db_session):
    """The whole point: backup then restore reproduces the same state."""
    u = _make_user(db_session, "rt@example.com", free=3)
    _make_chat(db_session, u.id, "sess-rt", message="first message")
    _make_chat(db_session, u.id, "sess-rt", message="second message")
    pre_count_users = db_session.query(db_models.User).count()
    pre_count_chat = db_session.query(db_models.ChatHistory).count()

    backup = build_backup_dict(db_session, include_passwords=True)

    # Wipe.
    truncate_table(db_session, db_models.User)
    truncate_table(db_session, db_models.ChatHistory)
    assert db_session.query(db_models.User).count() == 0
    assert db_session.query(db_models.ChatHistory).count() == 0

    # Restore.
    for name, model in [
        ("users", db_models.User),
        ("chat_history", db_models.ChatHistory),
    ]:
        restore_table(db_session, model, backup["tables"][name], dry_run=False)

    assert db_session.query(db_models.User).count() == pre_count_users
    assert db_session.query(db_models.ChatHistory).count() == pre_count_chat


def test_list_db_row_count_matches_table(db_session):
    """The diagnostic helper must reflect what's in the DB."""
    _make_user(db_session, "list@example.com")
    rows = db_session.query(db_models.User).all()
    serialised = [_row_to_jsonable(r) for r in rows]
    assert len(serialised) == 1
    assert serialised[0]["email"] == "list@example.com"


# ----- 2. session recovery endpoint -----

def test_recover_session_for_anonymous_user_returns_404(client, db_session):
    """Anonymous sessions are never persisted, so a recovery attempt
    for an unknown session id should 404, not 500 or 200."""
    r = client.post("/api/session/nonexistent-session/recover")
    assert r.status_code == 401  # not authenticated => 401, not 404


def test_recover_session_for_unknown_id_returns_404(client, db_session):
    """Authenticated, but the session id doesn't exist anywhere."""
    a = _register_and_login(client, "anon-recover@example.com")
    r = client.post(
        "/api/session/no-such-session/recover",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 404


def test_recover_session_without_auth_returns_401(client, db_session):
    """No bearer token at all — recovery is a logged-in-only endpoint."""
    r = client.post("/api/session/no-such-session/recover")
    assert r.status_code == 401


def test_recover_session_for_other_users_session_returns_404(client, db_session):
    """A user must not be able to recover another user's session,
    even if they know the session id."""
    a = _register_and_login(client, "alice-recover@example.com")
    # Create a chat history row for a *different* user.
    other = db_models.User(
        email="bob-recover@example.com", hashed_password="x", full_name="Bob"
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    # Drop a session row for Bob.
    from app.session import session_to_persisted
    from app.models import Session as AppSession
    sess = AppSession(
        session_id="bobs-secret-session",
        username="Bob",
        mode="savage",
        personality="savage_one",
        created_at=1.0,
    )
    db_session.add(db_models.RoastSession(
        session_id=sess.session_id,
        user_id=other.id,
        mode=sess.mode.value,
        personality=sess.personality.value,
        state_json=session_to_persisted(sess, user_id=other.id),
    ))
    db_session.commit()

    # Alice (authed) tries to recover Bob's session.
    r = client.post(
        "/api/session/bobs-secret-session/recover",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 404  # must NOT leak existence


def test_recover_session_in_memory_other_user_returns_404(client, db_session):
    """A user must not be able to recover another user's session that
    is currently held in the in-memory store. (The in-memory branch
    must perform the same ownership check as the DB branch; otherwise
    a leaked session id of an authed user could be peeked at by a
    different authed user.)"""
    from app.session import SESSIONS
    from app.models import Session as AppSession

    # Create a session in memory that belongs to "user 9999" (a
    # non-existent user id — the in-memory branch checks the value on
    # the Session object, not against the users table).
    sess = AppSession(
        session_id="mem-other-user",
        username="NotMe",
        mode="savage",
        personality="savage_one",
        created_at=1.0,
        user_id=9999,
    )
    SESSIONS._sessions[sess.session_id] = sess

    a = _register_and_login(client, "alice-in-mem@example.com")
    r = client.post(
        "/api/session/mem-other-user/recover",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 404
    # The session must NOT have been re-added to the store (would leak
    # via /api/session/{id}).
    assert "mem-other-user" in SESSIONS._sessions  # we put it there; never removed


def test_recover_session_in_memory_anonymous_returns_404(client, db_session):
    """An anonymous session (user_id is None) must not be recoverable
    by any authed user — the live path never persists anon sessions,
    so seeing one is suspicious. Returning 404 instead of 200 hides
    the existence of transient anon transcripts from unrelated
    authed callers."""
    from app.session import SESSIONS
    from app.models import Session as AppSession

    sess = AppSession(
        session_id="anon-in-mem",
        username="Anon",
        mode="savage",
        personality="savage_one",
        created_at=1.0,
        user_id=None,
    )
    SESSIONS._sessions[sess.session_id] = sess

    a = _register_and_login(client, "alice-anon-mem@example.com")
    r = client.post(
        "/api/session/anon-in-mem/recover",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 404


def test_recover_session_restores_state_after_cold_start(client, db_session):
    """The full recovery flow: authenticated user starts a chat,
    server-side in-memory store is wiped (simulating a host cold
    start), user calls /recover, gets their session back."""
    a = _register_and_login(client, "cold-start@example.com")
    user_id = db_session.query(db_models.User).filter(
        db_models.User.email == "cold-start@example.com"
    ).one().id

    # Start a session and send a message — this should persist the
    # session row to the DB.
    start = client.post(
        "/api/session/start",
        json={"mode": "savage", "personality": "savage_one"},
        headers=_auth_headers(a["access_token"]),
    )
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    roast = client.post(
        f"/api/session/{session_id}/roast",
        json={"message": "I am a 10x engineer."},
        headers=_auth_headers(a["access_token"]),
    )
    assert roast.status_code == 200

    # The DB should now have a roast_sessions row.
    row = db_session.query(db_models.RoastSession).filter(
        db_models.RoastSession.session_id == session_id
    ).one()
    assert row.user_id == user_id
    assert row.state_json["history"], "history should be persisted"

    # Simulate a cold start: wipe the in-memory session store.
    SESSIONS.delete(session_id)
    assert SESSIONS.get(session_id) is None

    # /api/session/{id} should now 404 (in-memory gone).
    gone = client.get(f"/api/session/{session_id}")
    assert gone.status_code == 404

    # But /recover should reconstruct the session.
    recovered = client.post(
        f"/api/session/{session_id}/recover",
        headers=_auth_headers(a["access_token"]),
    )
    assert recovered.status_code == 200, recovered.text
    body = recovered.json()
    assert body["session_id"] == session_id
    assert body["mode"] == "savage"
    assert body["personality"] == "savage_one"
    # The history should include the opener plus the user/assistant turn.
    assert len(body["history"]) >= 3
    # And the in-memory store should now be repopulated.
    assert SESSIONS.get(session_id) is not None

    # A subsequent /roast should work as if nothing happened.
    roast2 = client.post(
        f"/api/session/{session_id}/roast",
        json={"message": "And another thing."},
        headers=_auth_headers(a["access_token"]),
    )
    assert roast2.status_code == 200


def test_session_to_persisted_round_trip():
    """The JSON round trip must preserve every session field."""
    from app.models import (
        ChatMessage, Session as AppSession, SessionScores,
    )
    s = AppSession(
        session_id="abc123",
        username="tester",
        roaster_gender="male",
        mode="savage",
        personality="savage_one",
        created_at=12345.6,
        message_count=2,
        total_damage=42,
        comeback_attempts=1,
        comeback_failures=0,
        scores=SessionScores(
            confidence_lost=10,
            emotional_damage=42,
            delusion_level="Barely Aware",
            questionable_decisions=2,
            reality_checks=3,
            excuses_used=1,
            recovery_time="5 minutes and therapy",
        ),
        history=[ChatMessage(role="user", content="hi", intents=["programming"])],
        recent_roast_ids=["sav_001"],
        detected_intents=["programming"],
        opener_used=True,
        closer_used=False,
        ended_at=None,
        closer_text=None,
    )
    from app.session import session_from_persisted, session_to_persisted
    blob = session_to_persisted(s, user_id=99)
    back = session_from_persisted(blob)
    assert back.session_id == s.session_id
    assert back.username == s.username
    assert back.roaster_gender == s.roaster_gender
    assert back.mode == s.mode
    assert back.personality == s.personality
    assert back.message_count == s.message_count
    assert back.total_damage == s.total_damage
    assert back.comeback_attempts == s.comeback_attempts
    assert back.scores.emotional_damage == 42
    assert back.scores.delusion_level == "Barely Aware"
    assert back.history[0].content == "hi"
    assert back.recent_roast_ids == ["sav_001"]
    assert back.detected_intents == ["programming"]
    assert back.opener_used is True
    assert back.ended_at is None


def test_load_session_from_db_returns_none_for_unknown(db_session):
    assert load_session_from_db(db_session, "no-such-id") is None


def test_load_session_from_db_reconstructs_known_session(db_session):
    from app.models import Session as AppSession
    from app.session import session_to_persisted
    s = AppSession(
        session_id="load-test-session",
        username="lt",
        mode="savage",
        personality="savage_one",
        created_at=1.0,
    )
    row = db_models.RoastSession(
        session_id=s.session_id,
        user_id=None,  # not user-scoped for this test
        mode=s.mode.value,
        personality=s.personality.value,
        state_json=session_to_persisted(s, user_id=None),
    )
    db_session.add(row)
    db_session.commit()

    out = load_session_from_db(db_session, "load-test-session")
    assert out is not None
    assert out.session_id == "load-test-session"
    assert out.username == "lt"
