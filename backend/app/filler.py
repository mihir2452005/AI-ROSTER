"""Placeholder filling.

Supports 5 placeholder types: enum, context, intent, history, username.
For shorthand (a bare list of values), treats as enum.
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Any, Optional

from .library import Library
from .models import (
    PlaceholderSpec,
    Personality,
    RoastTemplate,
    Session,
    normalize_placeholder,
)

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def fill_placeholders(
    template: RoastTemplate,
    library: Library,
    session: Session,
    detected_intents: list[str],
) -> str:
    """Replace {placeholder} tokens with concrete values."""
    return _fill_in_text(
        text=template.template,
        placeholders=template.placeholders,
        library=library,
        session=session,
        detected_intents=detected_intents,
    )


def fill_placeholders_by_spec(
    template,
    library: Library,
    session: Session,
    prior_intent: Optional[str] = None,
    detected_intents: Optional[list[str]] = None,
) -> str:
    """Same as fill_placeholders, but for a SpecialTemplate (or any object
    with .template and .placeholders attributes)."""
    intents = detected_intents if detected_intents is not None else (
        session.detected_intents if prior_intent is None else [prior_intent]
    )
    return _fill_in_text(
        text=template.template,
        placeholders=template.placeholders,
        library=library,
        session=session,
        detected_intents=intents,
    )


def _fill_in_text(
    text: str,
    placeholders: dict,
    library: Library,
    session: Session,
    detected_intents: list[str],
) -> str:
    for name in PLACEHOLDER_RE.findall(text):
        if name not in placeholders:
            continue
        raw = placeholders[name]
        spec = normalize_placeholder(raw)
        value = _resolve(spec, name, library, session, detected_intents)
        text = text.replace("{" + name + "}", value)
    return text


def _resolve(
    spec: PlaceholderSpec,
    name: str,
    library: Library,
    session: Session,
    detected_intents: list[str],
) -> str:
    if spec.type == "enum":
        if spec.values:
            return random.choice(spec.values)
        if spec.default:
            return spec.default
        return "something"

    if spec.type == "context":
        return _context_value(name, spec)

    if spec.type == "intent":
        if detected_intents:
            intent = detected_intents[0]
            return _intent_phrase(intent, library)
        if spec.default:
            return spec.default
        return "your thing"

    if spec.type == "history":
        # Pull from the last_roast context we attach to the session
        return _history_value(name, session, spec)

    if spec.type == "username":
        return session.username or spec.default or "friend"

    if spec.type == "roaster":
        return _roaster_value(name, session, spec)

    return spec.default or "..."


# ---- Roaster (gender-aware) placeholders ----
# When the user picks a male/female/neutral roaster, the templates can use
# placeholders like {roaster_pronoun}, {roaster_title}, {roaster_self}, etc.,
# to produce personalized roasts that match the persona the user chose.
# This is a clean opt-in: existing templates without these placeholders are
# unaffected. New templates added to the library can use them freely.
_ROASTER_GENDERS = ("male", "female", "neutral")


def _roaster_value(name: str, session: Session, spec: PlaceholderSpec) -> str:
    gender = (session.roaster_gender or "neutral").lower()
    if gender not in _ROASTER_GENDERS:
        gender = "neutral"
    # Spec values may be {male: ..., female: ..., neutral: ..., default: ...}
    values = spec.values or []
    by_gender: dict[str, str] = {}
    for v in values:
        if ":" in v:
            k, _, val = v.partition(":")
            by_gender[k.strip().lower()] = val.strip()
    # Try the requested gender, then neutral, then default, then a sensible fallback.
    if gender in by_gender:
        return by_gender[gender]
    if "neutral" in by_gender:
        return by_gender["neutral"]
    if spec.default:
        return spec.default
    return _roaster_default(name, gender)


def _roaster_default(name: str, gender: str) -> str:
    """Built-in defaults for the most common roaster placeholders."""
    if name == "roaster_pronoun":
        return {"male": "he", "female": "she"}.get(gender, "they")
    if name == "roaster_pronoun_obj":
        return {"male": "him", "female": "her"}.get(gender, "them")
    if name == "roaster_pronoun_poss":
        return {"male": "his", "female": "her"}.get(gender, "their")
    if name == "roaster_self":
        return {"male": "man", "female": "lady"}.get(gender, "friend")
    if name == "roaster_title":
        return {"male": "sir", "female": "ma'am"}.get(gender, "friend")
    if name == "roaster_adjective":
        return {"male": "handsome", "female": "gorgeous"}.get(gender, "wonderful")
    return "—"


def _context_value(name: str, spec: PlaceholderSpec) -> str:
    if spec.values:
        return random.choice(spec.values)
    if spec.default:
        return spec.default
    # Default context values per placeholder name
    defaults = {
        "time_of_day": _time_of_day(),
        "day": datetime.now().strftime("%A"),
    }
    return defaults.get(name, spec.default or "right now")


def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 6:  return "the small hours"
    if h < 12: return "this morning"
    if h < 17: return "this afternoon"
    if h < 21: return "tonight"
    return "the late hours"


def _intent_phrase(intent: str, library: Library) -> str:
    """Turn an intent into a roast-friendly noun phrase."""
    phrases = {
        "programming": "your code",
        "school":      "your GPA",
        "gaming":      "your K/D",
        "fitness":     "your 'fitness journey'",
        "money":       "your finances",
        "relationships": "your love life",
        "career":      "your career",
    }
    return phrases.get(intent, f"your {intent}")


def _history_value(name: str, session: Session, spec: PlaceholderSpec) -> str:
    """Pull a value from the session's last-roast context.

    The lookup key is taken from spec.key (preferred) or the placeholder name.
    """
    # Predefined history keys (use spec.key if present, otherwise the name)
    key = (spec.key or name).lower()

    history_map = {
        "last_topic_summary":       lambda s: f"talked about {s.detected_intents[-1]}" if s.detected_intents else "rambled about something",
        "last_session_damage_pct":  lambda s: str(s.scores.emotional_damage),
        "roasts_received":          lambda s: str(s.scores.reality_checks),
        "comeback_attempts":        lambda s: str(s.comeback_attempts),
        "recurring_topic":          lambda s: f"into {s.detected_intents[0]}" if s.detected_intents else "being yourself",
    }

    if key in history_map:
        return history_map[key](session)

    return spec.default or "earlier"
