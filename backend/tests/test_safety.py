"""Safety filter tests.

Covers: self-harm detection, distress detection, PII detection, minor lock,
output blocklist scanning, and end-to-end API integration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import safety
from app.library import LIB
from app.models import Personality, RoastMode
from main import app


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ----- Input filter: self-harm -----

@pytest.mark.parametrize("msg", [
    "i want to kill myself",
    "I want to end my life",
    "I'm feeling suicidal",
    "I've been self-harming",
    "I'm cutting my arm",
    "i want to die",
    "no reason to live",
    "i don't want to live",
    "i overdosed on pills",
])
def test_self_harm_detected(msg):
    v = safety.check_input(msg)
    assert v.is_safe is False
    assert v.is_self_harm is True
    assert v.reply_override


def test_self_harm_api_short_circuits(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "I want to kill myself",
    })
    assert r.status_code == 200
    body = r.json()
    assert "someone" in body["roast"].lower() or "help" in body["roast"].lower()
    assert body["intents_detected"] == []
    assert body["template_id"] is None


# ----- Input filter: distress -----

@pytest.mark.parametrize("msg", [
    "i'm so depressed",
    "I'm feeling down",
    "i feel so alone",
    "i feel empty",
    "i can't take this anymore",
    "nobody likes me",
    "i'm anxious all the time",
])
def test_distress_detected(msg):
    v = safety.check_input(msg)
    assert v.is_safe is False
    assert v.is_distress is True


def test_distress_api_returns_safe_reply(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "i'm so depressed",
    })
    body = r.json()
    assert r.status_code == 200
    assert body["template_id"] is None


# ----- Input filter: PII -----

@pytest.mark.parametrize("msg", [
    "my ssn is 123-45-6789",
    "call me at (555) 123-4567",
    "my email is john@example.com",
    "my credit card is 4111 1111 1111 1111",
    "my address is 123 main street",
])
def test_pii_detected(msg):
    v = safety.check_input(msg)
    assert v.is_safe is False
    assert v.has_pii is True


def test_pii_api_blocks_roast(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "call me at (555) 123-4567 please",
    })
    body = r.json()
    assert "personal info" in body["roast"].lower()


# ----- Input filter: minors -----

@pytest.mark.parametrize("msg", [
    "i'm 14 years old",
    "I'm 17 y.o.",
    "i'm in middle school",
    "i'm in high school",
    "i'm a teenager",
    "i'm a minor",
    "i'm underage",
    "i'm 15 years old",
    "i'm in grade 9",
])
def test_minor_detected(msg):
    v = safety.check_input(msg)
    assert v.is_safe is False
    assert v.is_minor is True
    assert v.forced_mode == RoastMode.FRIENDLY
    assert v.forced_personality == Personality.SARCASTIC_FRIEND


def test_minor_locks_session_to_friendly(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/roast", json={
        "message": "i'm 14 years old",
    })
    assert r.status_code == 200
    # Session mode/personality should now be friendly + sarcastic_friend
    r = client.get(f"/api/session/{sid}")
    body = r.json()
    assert body["mode"] == "friendly"
    assert body["personality"] == "sarcastic_friend"


def test_minor_followup_uses_safe_personalities(client):
    r = client.post("/api/session/start", json={
        "mode": "savage", "personality": "savage_one",
    })
    sid = r.json()["session_id"]
    # First message: trigger minor detection
    client.post(f"/api/session/{sid}/roast", json={"message": "i'm 14"})
    # Second message: should stay friendly
    r = client.post(f"/api/session/{sid}/roast", json={"message": "hello there"})
    assert r.status_code == 200
    r = client.get(f"/api/session/{sid}")
    assert r.json()["mode"] == "friendly"
    assert r.json()["personality"] == "sarcastic_friend"


# ----- Output filter -----

def test_check_output_empty_blocklist():
    """When the blocklist is empty, everything passes."""
    v = safety.check_output("anything goes here")
    assert v.is_safe is True


def test_sanitize_output_empty_blocklist():
    assert safety.sanitize_output("don't change me") == "don't change me"


def test_check_output_finds_blocked_term(monkeypatch):
    """Inject a term into the blocklist and verify it's caught."""
    monkeypatch.setattr(safety, "BLOCKED_TERMS", frozenset({"forbiddenword"}))
    v = safety.check_output("this is a forbiddenword test")
    assert v.is_safe is False
    assert v.blocked_term_in_output == "forbiddenword"


def test_sanitize_output_redacts(monkeypatch):
    monkeypatch.setattr(safety, "BLOCKED_TERMS", frozenset({"forbiddenword"}))
    out = safety.sanitize_output("this is a FORBIDDENWORD test")
    assert "forbiddenword" not in out.lower()
    assert "[redacted]" in out


# ----- Policy helper -----

def test_apply_policy_locks_minor():
    mode, personality = safety.apply_policy(
        RoastMode.SAVAGE, Personality.SAVAGE_ONE, is_minor=True
    )
    assert mode == RoastMode.FRIENDLY
    assert personality == Personality.SARCASTIC_FRIEND


def test_apply_policy_passes_through_adult():
    mode, personality = safety.apply_policy(
        RoastMode.SAVAGE, Personality.SAVAGE_ONE, is_minor=False
    )
    assert mode == RoastMode.SAVAGE
    assert personality == Personality.SAVAGE_ONE


# ----- Safe messages pass through -----

@pytest.mark.parametrize("msg", [
    "i just bombed the interview",
    "my code doesn't compile",
    "i went to the gym today",
    "my ex texted me",
    "i'm doing fine thanks",
    "tell me a joke",
])
def test_safe_messages_pass(msg):
    v = safety.check_input(msg)
    assert v.is_safe is True
    assert v.reply_override is None


# ----- Regression: previously false-positive content now passes -----

def test_false_positive_pushed_to_main_passes():
    """The classic 'I pushed to main' message must not trigger a safety check."""
    v = safety.check_input("I pushed to main on Friday")
    assert v.is_safe is True


def test_false_positive_support_ticket_passes():
    v = safety.check_input("support ticket opened")
    assert v.is_safe is True
