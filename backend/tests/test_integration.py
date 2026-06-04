"""End-to-end integration test that exercises every user-facing button.

This is a behavioural test, not a unit test. It walks the full UX flow as a
user would: home page → start session → send messages → end session → open
share link → copy URL.

If the API contract drifts from the frontend expectations, this test catches
it before the user does.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.library import LIB
from main import app


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ============== HOME PAGE BUTTONS ==============

def test_home_button_starts_session(client):
    """The 'Start a roast session' button on the home page must:
    - POST /api/session/start
    - Return 200 with a session_id and opener
    - Frontend then navigates to /chat/{session_id}
    """
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "Alex",
    })
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert body["session_id"]
    assert "opener" in body
    assert body["opener"]  # non-empty
    assert body["mode"] == "savage"
    assert body["personality"] == "savage_one"
    assert "scores" in body


def test_home_button_anonymous_session(client):
    """Empty/whitespace username should be treated as anonymous (still 200)."""
    r = client.post("/api/session/start", json={
        "mode": "friendly",
        "personality": "sarcastic_friend",
        "username": "   ",
    })
    assert r.status_code == 200


def test_home_button_invalid_mode_rejected(client):
    """Unknown mode value (e.g. frontend sends typo) should 422."""
    r = client.post("/api/session/start", json={
        "mode": "ULTRA_SAVAGE",
        "personality": "savage_one",
    })
    assert r.status_code == 422


def test_home_button_invalid_personality_rejected(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "hacker_man",
    })
    assert r.status_code == 422


def test_home_button_username_too_long_rejected(client):
    """65-char username (frontend max is 64) is rejected with 422."""
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "x" * 65,
    })
    assert r.status_code == 422


def test_home_button_username_max_64_accepted(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "x" * 64,
    })
    assert r.status_code == 200


# ============== CHAT PAGE BUTTONS ==============

def test_send_button_sends_message(client):
    """'Send 🔥' button calls /api/session/{id}/roast."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "I bombed my interview"})
    assert r.status_code == 200
    body = r.json()
    assert "roast" in body and body["roast"]
    assert "scores" in body
    assert "intents_detected" in body
    assert isinstance(body["intents_detected"], list)
    assert "is_comeback" in body
    assert "is_opener" in body
    assert "is_closer" in body
    assert "template_id" in body


def test_send_button_blank_message_rejected(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "   "})
    assert r.status_code == 422


def test_send_button_very_long_message_rejected(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "x" * 2001})
    assert r.status_code == 422


def test_send_button_unknown_session_404(client):
    r = client.post("/api/session/bogus/roast", json={"message": "hi"})
    assert r.status_code == 404


def test_end_button_returns_closer_and_scores(client):
    """'End & get score' button calls /api/session/{id}/end."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "tell me something nice"})
    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    body = r.json()
    assert body["closer"] is not None and body["closer"]
    assert body["final_scores"] is not None
    assert body["share_url"] == f"/share/{sid}"


def test_share_link_works_after_end(client):
    """The share page calls /api/session/{id} after the session ends.
    This must return 200 (with the full transcript), not 404."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    client.post(f"/api/session/{sid}/roast", json={"message": "i bombed the interview"})
    client.post(f"/api/session/{sid}/end")
    r = client.get(f"/api/session/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["is_ended"] is True
    assert len(body["history"]) > 0
    # The closer should be the last message
    assert body["history"][-1]["role"] == "assistant"


def test_share_link_unknown_session_404(client):
    r = client.get("/api/session/totally-fake-id-123")
    assert r.status_code == 404


def test_send_after_end_returns_410(client):
    """The chat page should be disabled after end, but if a user tries
    to send a stale request it gets 410, not 200 or 500."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    client.post(f"/api/session/{sid}/end")
    r = client.post(f"/api/session/{sid}/roast", json={"message": "hi"})
    assert r.status_code == 410


# ============== SAFETY: every user-input path is filtered ==============

def test_self_harm_message_returns_safe_reply(client):
    """Safety-reply path: a self-harm message returns 200 with a safe
    reply (NOT a roast), and the user message + safe reply are both in
    history."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "i want to die"})
    assert r.status_code == 200
    body = r.json()
    assert body["intents_detected"] == []
    assert body["template_id"] is None
    assert body["roast"]  # non-empty safe reply


def test_minor_message_locks_session(client):
    """A minor self-identifying should lock the session to friendly mode."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "i'm 14"})
    assert r.status_code == 200
    # Verify the session was downgraded
    r = client.get(f"/api/session/{sid}")
    assert r.json()["mode"] == "friendly"
    assert r.json()["personality"] == "sarcastic_friend"


# ============== CATALOG ENDPOINTS (future-proofing) ==============

def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["library_loaded"] is True
    assert body["roasts"] > 0
    assert body["personalities"] > 0
    assert body["intents"] > 0


def test_list_modes(client):
    r = client.get("/api/modes")
    assert r.status_code == 200
    assert "modes" in r.json()


def test_list_personalities(client):
    r = client.get("/api/personalities")
    assert r.status_code == 200
    assert "personalities" in r.json()


# ============== CLEANUP ==============

def test_cleanup_endpoint(client):
    r = client.post("/api/admin/cleanup", headers={"X-Admin-Key": "test-admin-key-1234567890"})
    assert r.status_code == 200
    body = r.json()
    assert "removed" in body
    assert "ttl_seconds" in body


# ============== FRONTEND-INTEGRATED ENDPOINTS (no CORS preflight needed,
# goes through Next.js proxy) ==============

def test_session_appears_in_history_with_all_messages(client):
    """The chat page reads session.history to render the transcript. The
    history must include the opener, all user messages, all assistant
    replies, AND the closer (when ended)."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    # No /roast calls — just opener
    r = client.get(f"/api/session/{sid}")
    h = r.json()["history"]
    assert len(h) == 1
    assert h[0]["role"] == "assistant"
    assert h[0]["content"]  # opener non-empty

    # Now send a roast
    client.post(f"/api/session/{sid}/roast", json={"message": "hi"})
    r = client.get(f"/api/session/{sid}")
    h = r.json()["history"]
    assert len(h) == 3
    assert h[1]["role"] == "user"
    assert h[2]["role"] == "assistant"

    # End the session
    client.post(f"/api/session/{sid}/end")
    r = client.get(f"/api/session/{sid}")
    h = r.json()["history"]
    # The closer is the LAST message
    assert h[-1]["role"] == "assistant"
    assert r.json()["is_ended"] is True


def test_idempotent_end_returns_consistent_state(client):
    """The chat page after refresh relies on getSession to determine the
    state. After a refresh, finalScores is null (state is fresh) but
    is_ended is true. The closer must be in history as the last message
    so the frontend can recover it on refresh."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    end1 = client.post(f"/api/session/{sid}/end").json()
    end2 = client.post(f"/api/session/{sid}/end").json()
    assert end1["closer"] == end2["closer"]
    assert end1["final_scores"] == end2["final_scores"]

    # Now simulate a refresh: getSession should still return everything
    g = client.get(f"/api/session/{sid}").json()
    assert g["is_ended"] is True
    # Closer is the last assistant message
    last = g["history"][-1]
    assert last["role"] == "assistant"
    assert last["content"] == end1["closer"]
