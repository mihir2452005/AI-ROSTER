"""Session score calculation.

Mirrors the formulas in roast-library/scores.json.
"""
from __future__ import annotations

import re

from .models import Session, SessionScores

# Matches the kind of excuse language we want to count.
EXCUSE_REGEX = re.compile(
    r"\b(it\s+wasn'?t\s+my\s+fault|technically|that\s+doesn'?t\s+count|in\s+my\s+defense)\b",
    re.IGNORECASE,
)


def update_scores(session: Session, damage_added: int) -> None:
    """Recompute all scores after a turn.

    `damage_added` is kept in the signature for future tuning; the current
    formula derives everything from cumulative session state.
    """
    s = session.scores
    s.reality_checks = session.message_count
    # Confidence lost tracks roast damage plus the embarrassment of failed
    # clap-backs (each one knocks 5 points off the user's confidence).
    s.confidence_lost = min(
        100,
        int(session.total_damage * 0.6 + session.comeback_failures * 5),
    )
    s.emotional_damage = min(100, int(session.total_damage * 1.2))
    s.delusion_level = _tier(
        s.confidence_lost,
        [
            (0,  20,  "Mildly Aware"),
            (20, 40,  "Selectively Confused"),
            (40, 60,  "Confidently Wrong"),
            (60, 80,  "Main Character Syndrome"),
            (80, 101, "Full Reality TV Edit"),
        ],
    )
    s.recovery_time = _tier(
        s.emotional_damage,
        [
            (0,  20,  "15 minutes and a snack"),
            (20, 40,  "a long shower"),
            (40, 60,  "3 business days"),
            (60, 80,  "one full therapy arc"),
            (80, 101, "until next quarterly review"),
        ],
    )


def count_excuses(message: str) -> int:
    return len(EXCUSE_REGEX.findall(message))


def _tier(value: int, ladder: list[tuple[int, int, str]]) -> str:
    for lo, hi, label in ladder:
        if lo <= value < hi:
            return label
    return ladder[-1][2]


def fresh_scores() -> SessionScores:
    return SessionScores()
