"""Placeholder filling tests.

Validates all 6 placeholder types (enum, context, intent, history, username,
roaster) and the shorthand list syntax.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.filler import (
    _context_value,
    _history_value,
    _intent_phrase,
    fill_placeholders,
    fill_placeholders_by_spec,
)
from app.library import LIB
from app.models import (
    ChatMessage,
    Personality,
    PlaceholderSpec,
    RoastMode,
    Session,
    normalize_placeholder,
)


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


# ----- normalize_placeholder -----

def test_normalize_list_shorthand():
    spec = normalize_placeholder(["a", "b", "c"])
    assert spec.type == "enum"
    assert spec.values == ["a", "b", "c"]


def test_normalize_object_form():
    spec = normalize_placeholder({
        "type": "enum",
        "values": ["x"],
        "default": "y",
    })
    assert spec.type == "enum"
    assert spec.values == ["x"]
    assert spec.default == "y"


def test_normalize_empty_list_raises():
    with pytest.raises(ValueError):
        normalize_placeholder([])


def test_normalize_invalid_type_raises():
    with pytest.raises(Exception):
        normalize_placeholder("not a list or dict")


# ----- _resolve: enum -----

def test_enum_with_values():
    spec = PlaceholderSpec(type="enum", values=["a", "b", "c"])
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val in {"a", "b", "c"}


def test_enum_with_default_falls_back():
    spec = PlaceholderSpec(type="enum", default="hello")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val == "hello"


def test_enum_no_values_no_default():
    spec = PlaceholderSpec(type="enum")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val == "something"


# ----- _resolve: intent -----

def test_intent_uses_first_detected():
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    val = _intent_phrase("programming", LIB)
    assert val == "your code"


def test_intent_unknown_falls_back():
    val = _intent_phrase("unicorn", LIB)
    assert val == "your unicorn"


def test_resolve_intent_with_detected():
    spec = PlaceholderSpec(type="intent")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, ["school"])
    assert val == "your GPA"


def test_resolve_intent_without_detected_uses_default():
    spec = PlaceholderSpec(type="intent", default="your thing")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val == "your thing"


# ----- _resolve: username -----

def test_username_uses_session_username():
    spec = PlaceholderSpec(type="username")
    s = Session(session_id="x", username="Alice", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val == "Alice"


def test_username_falls_back_to_default():
    spec = PlaceholderSpec(type="username", default="friend")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val == "friend"


def test_username_falls_back_to_friend():
    spec = PlaceholderSpec(type="username")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val == "friend"


# ----- _resolve: context -----

def test_context_uses_values():
    spec = PlaceholderSpec(type="context", values=["ctx1", "ctx2"])
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    from app.filler import _resolve
    val = _resolve(spec, "p", LIB, s, [])
    assert val in {"ctx1", "ctx2"}


def test_context_uses_known_name():
    spec = PlaceholderSpec(type="context")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    val = _context_value("day", spec)
    assert val  # some day name


def test_context_unknown_name_falls_back():
    spec = PlaceholderSpec(type="context", default="never")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    val = _context_value("nonexistent_thing", spec)
    assert val == "never"


# ----- _resolve: history -----

def test_history_unknown_key_uses_default():
    spec = PlaceholderSpec(type="history", key="unknown_key", default="earlier")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    val = _history_value("p", s, spec)
    assert val == "earlier"


def test_history_uses_known_key():
    spec = PlaceholderSpec(type="history", key="roasts_received")
    from app.models import SessionScores
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
        scores=SessionScores(),
    )
    val = _history_value("p", s, spec)
    assert val == "0"


def test_history_with_no_session_history():
    spec = PlaceholderSpec(type="history", key="roasts_received")
    s = Session(session_id="x", mode=RoastMode.SAVAGE,
                personality=Personality.SAVAGE_ONE, created_at=0.0)
    val = _history_value("p", s, spec)
    assert val == "0"


# ----- End-to-end: every roast with placeholders can be filled -----

def test_every_roast_with_placeholders_can_be_filled():
    """Walk the whole library and try to fill any roast that has placeholders.
    None of them should leave {curly} tokens behind."""
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
        history=[ChatMessage(role="user", content="hi", intents=[])]
    )
    for mode in RoastMode:
        for r in LIB.roasts_for_mode(mode):
            if not r.placeholders:
                continue
            text = fill_placeholders(r, LIB, s, ["programming"])
            assert "{" not in text, f"{r.id} left unfilled: {text}"
            assert "}" not in text, f"{r.id} left unfilled: {text}"


# ----- Special templates get filled too -----

def test_opener_placeholder_fills():
    """Find any opener with placeholders and ensure it fills cleanly."""
    from app.matcher import select_opener
    from app.models import Personality, RoastMode
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
    )
    for o in LIB.openers:
        if o.placeholders:
            text = fill_placeholders_by_spec(o, LIB, s)
            assert "{" not in text
            return
    # If no opener has placeholders, that's fine - the test trivially passes.
    assert True


# ----- Roaster (gender-aware) placeholders -----
# These verify the new opt-in placeholder type that drives personalized roasts
# from the roaster gender the user picked at signup.

def test_roaster_placeholder_with_explicit_values():
    """If the template supplies male/female/neutral values, use them."""
    spec = PlaceholderSpec(
        type="roaster",
        values=["male:he", "female:she", "neutral:they"],
    )
    for gender, expected in [("male", "he"), ("female", "she"), ("neutral", "they")]:
        s = Session(
            session_id="x", mode=RoastMode.SAVAGE,
            personality=Personality.SAVAGE_ONE, created_at=0.0,
            roaster_gender=gender,
        )
        from app.filler import _resolve
        assert _resolve(spec, "roaster_pronoun", LIB, s, []) == expected


def test_roaster_placeholder_falls_back_to_neutral():
    """If a gender has no entry, fall back to neutral then to default."""
    spec = PlaceholderSpec(
        type="roaster",
        values=["neutral:they"],
        default="they",
    )
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
        roaster_gender="male",
    )
    from app.filler import _resolve
    # male is missing -> falls back to neutral
    assert _resolve(spec, "roaster_pronoun", LIB, s, []) == "they"


def test_roaster_placeholder_built_in_defaults():
    """Built-in defaults for the standard roaster_* placeholders."""
    from app.filler import _resolve
    expectations = {
        "roaster_pronoun":      ("male", "he"),
        "roaster_pronoun":      ("female", "she"),
        "roaster_pronoun":      ("neutral", "they"),
        "roaster_pronoun_obj":  ("male", "him"),
        "roaster_pronoun_poss": ("female", "her"),
        "roaster_title":        ("male", "sir"),
        "roaster_title":        ("female", "ma'am"),
        "roaster_self":         ("male", "man"),
        "roaster_self":         ("female", "lady"),
        "roaster_self":         ("neutral", "friend"),
    }
    for (name, (gender, expected)) in expectations.items():
        s = Session(
            session_id="x", mode=RoastMode.SAVAGE,
            personality=Personality.SAVAGE_ONE, created_at=0.0,
            roaster_gender=gender,
        )
        spec = PlaceholderSpec(type="roaster")
        assert _resolve(spec, name, LIB, s, []) == expected, (
            f"{name}/{gender} expected {expected!r}"
        )


def test_roaster_placeholder_unknown_gender_normalized_to_neutral():
    """Garbage roaster_gender values are treated as neutral at runtime.

    The Pydantic model rejects truly invalid values at the API boundary; the
    filler's runtime safety net handles anything that bypasses that check
    (e.g. legacy sessions loaded from an older schema) by coercing to
    neutral. We use model_construct to simulate such a session.
    """
    from app.filler import _resolve
    s = Session.model_construct(
        session_id="x", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
        roaster_gender="invalid_value",
    )
    spec = PlaceholderSpec(type="roaster")
    assert _resolve(spec, "roaster_pronoun", LIB, s, []) == "they"


def test_roaster_and_username_together_fills_cleanly():
    """End-to-end: a template with both {username} and {roaster_pronoun} fills without leftover braces."""
    from app.models import RoastTemplate
    t = RoastTemplate(
        id="tst_personalized",
        mode=RoastMode.SAVAGE,
        personalities=[Personality.SAVAGE_ONE],
        damage=5,
        tone="dry",
        template="Hey {username}, {roaster_pronoun} is watching.",
        placeholders={
            "username":        {"type": "username"},
            "roaster_pronoun": {
                "type": "roaster",
                "values": ["male:he", "female:she", "neutral:they"],
            },
        },
    )
    s = Session(
        session_id="x", mode=RoastMode.SAVAGE,
        personality=Personality.SAVAGE_ONE, created_at=0.0,
        username="Mihir",
        roaster_gender="female",
    )
    text = fill_placeholders(t, LIB, s, [])
    assert text == "Hey Mihir, she is watching."
    assert "{" not in text and "}" not in text
