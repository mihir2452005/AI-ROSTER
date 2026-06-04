"""Intent detection.

Pure keyword + phrase scan. No embeddings, no LLM. Fast, free, predictable.

Returns a ranked list of intent names with scores. Top intent is the dominant
topic; ties go to the intent with the higher library weight.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .library import Library


@dataclass
class IntentHit:
    name: str
    score: int
    label: str


def detect_intents(message: str, library: Library) -> list[IntentHit]:
    """Return intents ranked by score (highest first).

    Per-intent thresholds (intent.min_keyword_score) reduce false positives
    from over-broad keyword sets: programming/career/gaming require 2 hits
    to fire on keywords alone, while a single phrase match still triggers
    because phrases score 10× a keyword.
    """
    msg = message.lower()
    msg_words = set(re.findall(r"[a-z0-9+#./'-]+", msg))
    scoring = library.intent_scoring or {
        "exact_phrase_match": 10,
        "keyword_match": 1,
        "min_score_threshold": 1,
    }

    hits: list[IntentHit] = []
    for name, intent in library.intents.items():
        phrase_score = 0
        keyword_score = 0

        # Whole-phrase matches (substring)
        for phrase in intent.phrases:
            if phrase.lower() in msg:
                phrase_score += scoring["exact_phrase_match"]

        # Keyword matches (whole-word; multi-word keywords match as substring)
        for kw in intent.keywords:
            kw_low = kw.lower()
            if " " in kw_low or "-" in kw_low or "/" in kw_low:
                if kw_low in msg:
                    keyword_score += scoring["keyword_match"]
            elif kw_low in msg_words:
                keyword_score += scoring["keyword_match"]

        # Decide if this intent fires.
        # 1) Any phrase match -> always fires (phrases are deliberate).
        # 2) Keyword-only -> must meet per-intent or global threshold.
        fires = False
        if phrase_score > 0:
            fires = True
        else:
            threshold = (
                intent.min_keyword_score
                if intent.min_keyword_score is not None
                else scoring["min_score_threshold"]
            )
            if keyword_score >= threshold:
                fires = True

        if fires:
            total = (phrase_score + keyword_score) * intent.weight
            hits.append(IntentHit(name=name, score=total, label=intent.label))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def top_intent(message: str, library: Library) -> str | None:
    hits = detect_intents(message, library)
    return hits[0].name if hits else None


def top_intent_names(message: str, library: Library, k: int = 2) -> list[str]:
    """Return the top-k intent names (used for placeholder filling)."""
    return [h.name for h in detect_intents(message, library)[:k]]


# ----- Comeback detection -----

COMEBACK_SIGNALS = {
    "keywords": [
        "you too", "no u", "fight me", "come at me",
        "your mom", "your mother", "well actually", "actually,",
    ],
    "tone": ["defensive", "aggressive"],
}

CLAPBACK_REGEX = re.compile(
    r"(\byou('?re| are) (also|so) ['\"\w]+|"
    r"\bno (u|you)\b|"
    r"\bfight me\b|"
    r"\bcome at me\b|"
    r"\byour (mom|mother)\b|"
    r"!{2,}|"
    r"^(yeah|well|actually),?\s+[\w']+(\s+['\"])?)",
    re.IGNORECASE,
)


def is_comeback(message: str) -> bool:
    """Heuristic: is the user trying to clap back?

    Combines three signals: explicit comeback phrases, regex matches, and
    aggressive punctuation. All-caps ALONE doesn't count (would mis-fire on
    "HELLO THERE" or a polite all-caps question) — it has to be paired with
    a comeback phrase or come after aggressive punctuation.
    """
    msg = message.lower().strip()
    for kw in COMEBACK_SIGNALS["keywords"]:
        if kw in msg:
            return True
    if CLAPBACK_REGEX.search(message):
        return True
    # Multiple exclamation marks plus ALL CAPS is a real clap-back signal
    # (e.g. "NO U!!!!", "WHATEVER!!!"). Either alone is not.
    if "!!" in message and msg.isupper() and len(msg) > 5:
        return True
    return False
