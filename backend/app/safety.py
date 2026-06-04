"""Safety filters for RoastGPT.

Layer 1 (template engine) has no LLM guardrails, so we add explicit
safety checks at three points:

1. INPUT  - incoming user message: detect self-harm, doxxing attempts,
            protected-class probing, and minors.
2. OUTPUT - outgoing roast text: scan for anything we don't want to ship,
            even if a library author sneaks it in.
3. POLICY - lock under-18 users into friendly/sarcastic_friend, and prevent
            self-harm or doxx roasts from being delivered.

This module is intentionally conservative. False positives here are cheaper
than a real-world incident.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import Personality, RoastMode


# ----- Blocklist (output) -----
# Terms that must never appear in a delivered roast. Stored as a frozen
# lowercase set for O(1) lookup. Substrings and whole-words are both checked
# by the scan function.
#
# Categories: slurs against protected classes, explicit self-harm language,
# and explicit violence/sexual content. We keep this list in code (not JSON)
# because changing it should require a code review.
#
# NOTE: These are example terms for demonstration. In production, extend with
# actual blocklist based on your safety requirements.
BLOCKED_TERMS: frozenset[str] = frozenset(
    {
        # Example blocked terms (replace with real blocklist in production)
        "badword1",
        "badword2", 
        "badword3",
        # Racial / ethnic slurs (placeholders - real list lives in prod)
        # Add canonical slurs here; we keep placeholders in this public repo.
        # Disabled-class slurs
        # Gender / sexuality slurs
        # Religious slurs
        # No protected-class slurs are listed in this open-source file. The
        # production deployment extends this set internally.
    }
)


# Self-harm / suicide signals (input)
SELF_HARM_PATTERNS = [
    re.compile(r"\b(kill|end)\s+(my|my\s+own)\s+life\b", re.IGNORECASE),
    re.compile(r"\bkill\s+myself\b", re.IGNORECASE),
    re.compile(r"\bsuicid(e|al)\b", re.IGNORECASE),
    re.compile(r"\bself[- ]?harm(ing|ed)?\b", re.IGNORECASE),
    re.compile(r"\bcut(ting)?\s+(my|my\s+own)\s+(arm|leg|wrist|self)\b", re.IGNORECASE),
    re.compile(r"\bi\s+want\s+to\s+die\b", re.IGNORECASE),
    re.compile(r"\bno\s+reason\s+to\s+live\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+want\s+to\s+(live|be\s+alive)\b", re.IGNORECASE),
    re.compile(r"\boverdose(d|ing)?\s+on\b", re.IGNORECASE),
]


# Distress signals (input) - softer than self-harm, still triggers a safe reply.
DISTRESS_PATTERNS = [
    # "i'm depressed", "I'm so sad", "i'm feeling down", "i'm anxious"
    re.compile(
        r"\bi'?m\s+(?:so\s+|feeling\s+|such\s+a\s+)?"
        r"(depress(?:ed|ing)|sad|down|anxious|panick(?:ed|ing)|stressed|lonely|exhausted)\b",
        re.IGNORECASE,
    ),
    # "i feel alone", "i'm feeling empty"
    re.compile(
        r"\bi(?:\'?m|\s+am)\s+(?:feeling\s+|so\s+)?(alone|empty|hopeless|worthless|broken)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bi\s+feel\s+(so\s+)?(alone|empty|hopeless|worthless)\b", re.IGNORECASE),
    re.compile(r"\bi\s+can'?t\s+(take|cope|handle)\s+(it|this|anymore)\b", re.IGNORECASE),
    re.compile(r"\bmy\s+(whole\s+)?life\s+is\s+falling\s+apart\b", re.IGNORECASE),
    re.compile(r"\bnobody\s+(likes|loves|cares\s+about)\s+me\b", re.IGNORECASE),
]


# Personal-info patterns (input) - doxxing attempts.
PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\d\b"),
    "phone_us": re.compile(r"\b\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    "email": re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
    "address_hint": re.compile(r"\b(my\s+address\s+is|live\s+at\s+\d|home\s+address\s+is)\b", re.IGNORECASE),
}


def _minor_age_looks_legit(match: re.Match) -> bool:
    """The minor age must be 1-17 AND either followed by a year marker
    ('years old', 'y.o.', 'y/o') OR end the message — to avoid catching
    "i'm 9 to 5" or "i'm 12 hours late"."""
    raw = match.group(0)
    num = int(match.group(2))
    if not (1 <= num <= 17):
        return False
    has_year_marker = bool(
        re.search(r"\b(?:years?\s*old|y\.?o\.?|y\/o)\b", raw, re.IGNORECASE)
    )
    if has_year_marker:
        return True
    # Without a year marker, the age must be at end-of-string to count.
    return match.string.rstrip().endswith(raw.rstrip())


# Minors / under-18 signals (input). Conservative: any clear mention locks the
# session to safe defaults.
MINOR_PATTERNS = [
    re.compile(r"\bi'?m\s+(a\s+)?(\d{1,2})(?:\s*(?:years?\s*old|y\.?o\.?|y\/o))?\b", re.IGNORECASE),
    re.compile(r"\bi'?m\s+(in\s+)?(middle|high)\s+school\b", re.IGNORECASE),
    re.compile(r"\bi'?m\s+(a\s+)?(teenager|minor|under\s*18|underage)\b", re.IGNORECASE),
    re.compile(r"\bi'?m\s+in\s+(grade|gr)\s+\d{1,2}\b", re.IGNORECASE),
    re.compile(r"\bmy\s+parents\s+(don'?t|do\s+not)\s+let\b", re.IGNORECASE),
]


# ----- Safe mode defaults -----

SAFE_MODE = RoastMode.FRIENDLY
SAFE_PERSONALITY = Personality.SARCASTIC_FRIEND


SAFE_REFUSAL_LINES = [
    "I'm not the right tool for that. If you're going through something heavy, "
    "please talk to someone you trust or a professional who can help.",
    "I roast, but I don't joke about that. Reach out to someone who can help.",
    "That message had me worried for a second. For real: talk to someone. "
    "A friend, a family member, a hotline. You don't have to handle it alone.",
    "I'm going to pass on roasting that one. If you need support, please "
    "reach out to someone who can actually help.",
]

PII_REFUSAL_LINE = (
    "I noticed something that looks like personal info in your message. "
    "Please don't share addresses, phone numbers, or IDs in a chat with a "
    "roast bot. I'll just pretend I didn't see it."
)


@dataclass
class SafetyVerdict:
    """Result of running the safety filters."""
    is_safe: bool
    is_self_harm: bool = False
    is_distress: bool = False
    is_minor: bool = False
    has_pii: bool = False
    blocked_term_in_output: Optional[str] = None
    forced_mode: Optional[RoastMode] = None
    forced_personality: Optional[Personality] = None
    reply_override: Optional[str] = None


# ----- Public API -----

def check_input(message: str) -> SafetyVerdict:
    """Inspect an inbound user message before we do anything else with it."""
    verdict = SafetyVerdict(is_safe=True)

    for pat in SELF_HARM_PATTERNS:
        if pat.search(message):
            verdict.is_safe = False
            verdict.is_self_harm = True
            verdict.reply_override = SAFE_REFUSAL_LINES[0]
            return verdict

    for pat in DISTRESS_PATTERNS:
        if pat.search(message):
            verdict.is_safe = False
            verdict.is_distress = True
            verdict.reply_override = SAFE_REFUSAL_LINES[1]
            return verdict

    for label, pat in PII_PATTERNS.items():
        if pat.search(message):
            verdict.is_safe = False
            verdict.has_pii = True
            verdict.reply_override = PII_REFUSAL_LINE
            return verdict

    for pat in MINOR_PATTERNS:
        m = pat.search(message)
        if not m:
            continue
        # The age-detection pattern needs a guard against false positives.
        if pat.pattern.startswith("\\bi'?m\\s+(a\\s+)?(\\d{1,2})") and not _minor_age_looks_legit(m):
            continue
        verdict.is_safe = False
        verdict.is_minor = True
        verdict.forced_mode = SAFE_MODE
        verdict.forced_personality = SAFE_PERSONALITY
        verdict.reply_override = (
            "Got it - I'll keep things friendly and light. "
            "I won't go savage on you."
        )
        return verdict

    return verdict


def check_output(text: str) -> SafetyVerdict:
    """Inspect a generated roast before sending it back to the user.

    Returns a verdict whose `blocked_term_in_output` names the first blocked
    term found, if any.
    """
    if not BLOCKED_TERMS:
        return SafetyVerdict(is_safe=True)

    lower = text.lower()
    for term in BLOCKED_TERMS:
        if term in lower:
            return SafetyVerdict(is_safe=False, blocked_term_in_output=term)
    return SafetyVerdict(is_safe=True)


def sanitize_output(text: str) -> str:
    """Replace any blocked term with a redaction marker. Returns the cleaned
    text. Use this when you'd rather patch the roast than drop it.
    """
    if not BLOCKED_TERMS:
        return text
    lower_to_term = {t.lower(): t for t in BLOCKED_TERMS}
    for needle in lower_to_term:
        text = re.sub(re.escape(needle), "[redacted]", text, flags=re.IGNORECASE)
    return text


def apply_policy(
    mode: RoastMode,
    personality: Personality,
    *,
    is_minor: bool,
) -> tuple[RoastMode, Personality]:
    """Lock the user into safe defaults if they're a minor, otherwise return
    their selection unchanged.
    """
    if is_minor:
        return SAFE_MODE, SAFE_PERSONALITY
    return mode, personality
