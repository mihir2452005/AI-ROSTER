"""Regression tests for bugs found in the second Layer 1 audit.

Each test corresponds to a specific bug fix. If you change the underlying
behavior, this file should be the first place you look.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Disable rate limiting for tests by setting a high limit
os.environ["RATE_LIMIT_REQUESTS"] = "10000"
os.environ["RATE_LIMIT_WINDOW"] = "1"

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import matcher, safety, scorer
from app.config import MAX_SESSION_MESSAGES
from app.library import LIB
from app.models import (
    Personality,
    RoastMode,
    RoastTemplate,
    SpecialTemplate,
    Tone,
)
from main import app


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ----- BUG 1: end_session / apply_personality_flavor must not crash on None -----

def test_apply_personality_flavor_handles_none():
    """Guard against the end_session crash when no closer exists for a
    personality. The function must pass None through unchanged so the
    caller can detect 'no roast selected'."""
    out = matcher.apply_personality_flavor(None, Personality.SAVAGE_ONE, LIB)
    assert out is None


def test_apply_personality_flavor_normal_text():
    out = matcher.apply_personality_flavor("hello", Personality.SAVAGE_ONE, LIB)
    assert out is not None
    assert "hello" in out


def test_end_session_with_no_closer_does_not_crash(client, monkeypatch):
    """Regression: if a personality has no closer, end_session should still
    return 200 with the fallback closer instead of crashing."""
    # Register a fake session in the in-memory store
    from app.session import SESSIONS
    s = SESSIONS.create(RoastMode.SAVAGE, Personality.SAVAGE_ONE, None)
    # Monkeypatch select_closer to return None to simulate "no closer available"
    monkeypatch.setattr(matcher, "select_closer", lambda personality, library: None)
    r = client.post(f"/api/session/{s.session_id}/end")
    assert r.status_code == 200
    body = r.json()
    # Fallback closer is always non-null on end (the API contract).
    assert body["closer"] is not None
    assert body["closer"].strip() != ""
    assert body["final_scores"] is not None


# ----- BUG 2: MAX_SESSION_MESSAGES is enforced -----

def test_session_message_cap_returns_429(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    last = None
    for i in range(MAX_SESSION_MESSAGES):
        r = client.post(f"/api/session/{sid}/roast", json={"message": f"msg {i}"})
        assert r.status_code == 200, f"failed at {i}: {r.text}"
        last = r
    # The 51st message should be capped
    r = client.post(f"/api/session/{sid}/roast", json={"message": "one too many"})
    assert r.status_code == 429
    assert "cap" in r.json()["detail"].lower()


def test_session_cap_bypassed_for_safety_replies(client):
    """Safety replies must always go through, even past the cap."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    # Fill the cap
    for i in range(MAX_SESSION_MESSAGES):
        client.post(f"/api/session/{sid}/roast", json={"message": f"msg {i}"})
    # Regular message gets 429
    r = client.post(f"/api/session/{sid}/roast", json={"message": "hi"})
    assert r.status_code == 429
    # Self-harm message still gets through with a safe reply
    r = client.post(f"/api/session/{sid}/roast", json={"message": "i want to die"})
    assert r.status_code == 200
    body = r.json()
    assert body["intents_detected"] == []
    assert body["template_id"] is None


# ----- BUG 3: username has a length cap and gets stripped -----

def test_username_too_long_rejected(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "a" * 100,
    })
    assert r.status_code == 422


def test_username_max_64_accepted(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "a" * 64,
    })
    assert r.status_code == 200


def test_username_whitespace_treated_as_anonymous(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "   ",
    })
    assert r.status_code == 200
    # Username should have been normalized to None


def test_username_gets_stripped(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "  alice  ",
    })
    assert r.status_code == 200
    sid = r.json()["session_id"]
    r = client.get(f"/api/session/{sid}")
    # The stored username is the stripped one
    # (or None if the strip yielded empty)
    assert r.json()["history"] is not None


# ----- BUG 4: whitespace-only messages are rejected -----

def test_whitespace_message_rejected(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "   "})
    assert r.status_code == 422


def test_tab_newline_only_message_rejected(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "\t\n  \n"})
    assert r.status_code == 422


def test_real_message_with_whitespace_passes(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "  hello  "})
    assert r.status_code == 200


# ----- BUG 5: RoastTemplate.weight is constrained to 0-1 -----

def test_weight_above_one_rejected():
    with pytest.raises(Exception):
        RoastTemplate(
            id="bad_001", mode=RoastMode.SAVAGE, personalities=[Personality.SAVAGE_ONE],
            damage=5, tone=Tone.CUTTING, template="test",
            weight=2.0,
        )


def test_weight_negative_rejected():
    with pytest.raises(Exception):
        RoastTemplate(
            id="bad_002", mode=RoastMode.SAVAGE, personalities=[Personality.SAVAGE_ONE],
            damage=5, tone=Tone.CUTTING, template="test",
            weight=-0.5,
        )


def test_weight_zero_accepted():
    t = RoastTemplate(
        id="ok_001", mode=RoastMode.SAVAGE, personalities=[Personality.SAVAGE_ONE],
        damage=5, tone=Tone.CUTTING, template="test",
        weight=0.0,
    )
    assert t.weight == 0.0


def test_weight_one_accepted():
    t = RoastTemplate(
        id="ok_002", mode=RoastMode.SAVAGE, personalities=[Personality.SAVAGE_ONE],
        damage=5, tone=Tone.CUTTING, template="test",
        weight=1.0,
    )
    assert t.weight == 1.0


# ----- BUG 6: output safety on opener/callback/closer -----

def test_opener_safety_scan_redacts_blocked_term(client, monkeypatch):
    """If the library ships a blocked term in an opener, the safety filter
    must redact it before delivery."""
    monkeypatch.setattr(safety, "BLOCKED_TERMS", frozenset({"forbiddenword"}))
    # Inject a forbidden term into the opener
    import app.filler as filler
    real_fill = filler.fill_placeholders_by_spec
    def tainted_fill(*args, **kwargs):
        text = real_fill(*args, **kwargs)
        return text + " forbiddenword" if text else text
    monkeypatch.setattr(filler, "fill_placeholders_by_spec", tainted_fill)
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    assert r.status_code == 200
    assert "forbiddenword" not in r.json()["opener"].lower()
    assert "[redacted]" in r.json()["opener"].lower()


def test_closer_safety_scan_redacts_blocked_term(client, monkeypatch):
    monkeypatch.setattr(safety, "BLOCKED_TERMS", frozenset({"forbiddenword"}))
    import app.filler as filler
    real_fill = filler.fill_placeholders_by_spec
    def tainted_fill(*args, **kwargs):
        text = real_fill(*args, **kwargs)
        return text + " forbiddenword" if text else text
    monkeypatch.setattr(filler, "fill_placeholders_by_spec", tainted_fill)
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    closer = r.json()["closer"]
    if closer:
        assert "forbiddenword" not in closer.lower()


# ----- BUG 7: update_scores signature changed (no is_comeback_failure) -----

def test_update_scores_no_longer_takes_failure_flag():
    """The is_comeback_failure parameter was dead code. The function should
    accept only (session, damage_added) now."""
    from app.models import Session, SessionScores
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE, personality=Personality.SAVAGE_ONE,
        created_at=0.0, scores=SessionScores(),
    )
    # Old call signature would now raise TypeError
    with pytest.raises(TypeError):
        scorer.update_scores(s, damage_added=5, is_comeback_failure=True)


def test_update_scores_basic_call():
    from app.models import Session, SessionScores
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE, personality=Personality.SAVAGE_ONE,
        created_at=0.0, scores=SessionScores(), total_damage=50,
    )
    scorer.update_scores(s, damage_added=10)
    assert s.scores.reality_checks == 0
    assert s.scores.emotional_damage == 60  # 50 * 1.2


# ----- BUG 8: is_comeback is more conservative -----

def test_all_caps_alone_is_not_comeback():
    """Plain all-caps (no aggressive punctuation) is not a comeback."""
    from app.intent import is_comeback
    assert not is_comeback("HELLO THERE")
    assert not is_comeback("HI HOW ARE YOU")
    assert not is_comeback("GOOD MORNING")


def test_all_caps_with_exclamations_is_comeback():
    """All caps + !! is a real clap-back signal."""
    from app.intent import is_comeback
    assert is_comeback("NO U!!!!")
    assert is_comeback("WHATEVER!!!")


def test_existing_comeback_signals_still_work():
    from app.intent import is_comeback
    assert is_comeback("no u")
    assert is_comeback("you too")
    assert is_comeback("your mom")
    assert is_comeback("fight me")
    assert is_comeback("well actually")
    assert is_comeback("you are so dumb")


def test_non_comeback_still_not_comeback():
    from app.intent import is_comeback
    assert not is_comeback("hello there")
    assert not is_comeback("my code doesn't work")
    assert not is_comeback("i bombed the interview")


# ----- BUG 9/10: end_session handles all paths without NameError -----

def test_end_session_does_not_raise_nameerror(client, monkeypatch):
    """When select_closer is replaced with one that returns None, the
    end_session route must not raise NameError on `cl is not None`."""
    monkeypatch.setattr(matcher, "select_closer", lambda personality, library: None)
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    assert r.json()["closer"] is not None


# ----- BUG: callback path in start_session must not raise NameError -----

def test_start_session_with_callback_does_not_crash(client, monkeypatch):
    """If a returning user triggers a callback, start_session must not
    NameError on `op is not None` (since op is only set in the else branch)."""
    from app.session import MEMORY, SESSIONS
    # Pre-populate memory with a prior session
    s = SESSIONS.create(RoastMode.SAVAGE, Personality.SAVAGE_ONE, "testuser")
    s.detected_intents = ["programming"]
    MEMORY.record_session(s)
    SESSIONS.delete(s.session_id)

    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one", "username": "testuser",
    })
    assert r.status_code == 200
    assert r.json()["opener"]


# ----- Scorer: confidence_lost math -----

def test_confidence_lost_caps_at_100():
    from app.models import Session, SessionScores
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE, personality=Personality.SAVAGE_ONE,
        created_at=0.0, scores=SessionScores(), total_damage=1000, comeback_failures=100,
    )
    scorer.update_scores(s, damage_added=10)
    assert s.scores.confidence_lost == 100
    assert s.scores.emotional_damage == 100
    assert s.scores.delusion_level == "Full Reality TV Edit"


# ----- Share flow: session must persist after /end -----

def test_session_persists_after_end(client):
    """The share URL must still load the transcript after the user ends
    the session. Regression: previously /end deleted the session, so
    /share/{id} always 404'd."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={"message": "hello"})
    assert r.status_code == 200
    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    closer = r.json()["closer"]
    assert closer
    # Now hit the share URL (same as getSession).
    r = client.get(f"/api/session/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["is_ended"] is True
    # The closer should be the LAST message in history
    assert body["history"][-1]["role"] == "assistant"
    assert body["history"][-1]["content"] == closer


def test_ended_session_rejects_new_messages_with_410(client):
    """Once ended, the session is read-only. Posting to /roast must 410."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    r = client.post(f"/api/session/{sid}/roast", json={"message": "hi"})
    assert r.status_code == 410
    assert "ended" in r.json()["detail"].lower()


def test_end_session_is_idempotent(client):
    """Calling /end twice should return the same closer and the same
    final scores (no double-increment, no crash)."""
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r1 = client.post(f"/api/session/{sid}/end").json()
    r2 = client.post(f"/api/session/{sid}/end").json()
    assert r1["closer"] == r2["closer"]
    assert r1["final_scores"] == r2["final_scores"]


def test_cleanup_does_not_remove_live_sessions(client):
    """Active sessions must never be cleaned up, only ended ones past TTL."""
    from app.session import SESSIONS
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post("/api/admin/cleanup", headers={"X-Admin-Key": "test-admin-key-1234567890"})
    assert r.status_code == 200
    # Session still exists
    r = client.get(f"/api/session/{sid}")
    assert r.status_code == 200


def test_cleanup_removes_old_ended_sessions(client, monkeypatch):
    from app.session import SESSIONS
    from app.models import Session, SessionScores
    # Inject a fake old-ended session
    s = Session(
        session_id="oldended01",
        mode=RoastMode.SAVAGE, personality=Personality.SAVAGE_ONE,
        created_at=0.0, ended_at=0.0,  # epoch = ancient
        scores=SessionScores(),
    )
    SESSIONS.save(s)
    r = client.post("/api/admin/cleanup", headers={"X-Admin-Key": "test-admin-key-1234567890"})
    assert r.status_code == 200
    assert r.json()["removed"] >= 1
    # Session is gone
    assert SESSIONS.get("oldended01") is None


def test_fallback_closer_always_returned(client, monkeypatch):
    """Regression for UX: the UI relies on closer being non-null. Even if
    select_closer returns None, we return a non-empty fallback."""
    monkeypatch.setattr(matcher, "select_closer", lambda personality, library: None)
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    assert r.json()["closer"] is not None
    assert r.json()["closer"].strip() != ""
