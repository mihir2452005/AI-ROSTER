"""Smoke tests for the roast engine.

Run with: pytest backend/tests/
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `app` importable when running pytest from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.library import LIB
from main import app


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ----- Library -----

def test_library_loads():
    assert LIB.is_loaded()
    assert len(LIB.roasts_by_id) >= 150
    assert len(LIB.personalities) == 6
    assert len(LIB.intents) >= 6


def test_all_modes_have_roasts():
    from app.models import RoastMode
    for mode in RoastMode:
        assert len(LIB.roasts_for_mode(mode)) > 0, f"no roasts for {mode}"


# ----- API -----

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["library_loaded"] is True
    assert body["roasts"] > 0


def test_list_modes(client):
    r = client.get("/api/modes")
    assert r.status_code == 200
    assert "programmer" in r.json()["modes"]


def test_list_personalities(client):
    r = client.get("/api/personalities")
    assert r.status_code == 200
    assert "savage_one" in r.json()["personalities"]


# ----- End-to-end flow -----

def test_full_session_flow(client):
    r = client.post("/api/session/start", json={
        "mode": "savage",
        "personality": "savage_one",
        "username": "TestUser",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    sid = body["session_id"]
    assert body["opener"]
    assert body["scores"]["confidence_lost"] == 0

    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "My code doesn't compile and I think my CSS is broken",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["roast"]
    assert "programming" in body["intents_detected"]
    assert body["scores"]["reality_checks"] >= 1
    assert body["scores"]["emotional_damage"] > 0

    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "no u",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["is_comeback"] is True
    assert body["roast"]

    r = client.post(f"/api/session/{sid}/end")
    assert r.status_code == 200
    body = r.json()
    assert body["final_scores"]["reality_checks"] >= 2
    assert body["closer"]
    assert body["share_url"] == f"/share/{sid}"


def test_gamer_intent_detection(client):
    r = client.post("/api/session/start", json={
        "mode": "gamer",
        "personality": "gamer",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "My K/D ratio is so low, the enemy team is sending me thank you cards",
    })
    body = r.json()
    assert "gaming" in body["intents_detected"]
    assert body["roast"]


def test_friendly_mode_does_not_use_savage_roasts(client):
    r = client.post("/api/session/start", json={
        "mode": "friendly",
        "personality": "sarcastic_friend",
    })
    sid = r.json()["session_id"]
    # Send a few messages and make sure damage stays in friendly range
    for msg in ["hello", "how are you", "i'm doing fine", "thanks"]:
        r = client.post(f"/api/session/{sid}/roast", json={"message": msg})
        assert r.status_code == 200
    body = client.post(f"/api/session/{sid}/end").json()
    # Friendly mode should produce low overall damage
    assert body["final_scores"]["emotional_damage"] < 50


def test_unknown_session_returns_404(client):
    r = client.post("/api/session/nonexistent/roast", json={"message": "hi"})
    assert r.status_code == 404


# ----- Intent detection unit tests -----

def test_intent_detects_programming():
    from app.intent import detect_intents
    hits = detect_intents("my code has a bug in the function", LIB)
    assert "programming" in [h.name for h in hits]


def test_intent_detects_school():
    from app.intent import detect_intents
    hits = detect_intents("i have an exam tomorrow and i didn't study", LIB)
    assert "school" in [h.name for h in hits]


def test_intent_returns_empty_for_garbage():
    from app.intent import detect_intents
    hits = detect_intents("banana telephone xylophone", LIB)
    assert hits == []


def test_comeback_detection():
    from app.intent import is_comeback
    assert is_comeback("no u")
    assert is_comeback("your mom")
    assert is_comeback("FIGHT ME BRO")
    assert not is_comeback("hello there")


# ----- Placeholder filling -----

def test_placeholder_filling_unit():
    """Make sure placeholders get filled (no curly braces left)."""
    from app.filler import fill_placeholders
    from app.models import (
        ChatMessage, Personality, RoastMode, RoastTemplate, Session, Tone
    )
    session = Session(
        session_id="t1", username="Bob", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
        history=[ChatMessage(role="user", content="hi", intents=[])],
    )
    # Pick any general roast with a placeholder
    for r in LIB.roasts_for_mode(RoastMode.GENERAL):
        if r.placeholders:
            text = fill_placeholders(r, LIB, session, [])
            assert "{" not in text, f"unfilled: {text}"
            assert "}" not in text, f"unfilled: {text}"
            return
    assert False, "no general roast had placeholders to test"
