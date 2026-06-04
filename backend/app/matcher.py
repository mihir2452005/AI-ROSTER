"""Roast selection: filter candidates, score them, weighted-pick the winner."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Optional

from .config import RECENT_ROAST_WINDOW
from .filler import fill_placeholders
from .library import Library
from .models import Personality, RoastMode, RoastTemplate, Session


@dataclass
class ScoredRoast:
    template: RoastTemplate
    score: float
    reasons: list[str] = field(default_factory=list)


def select_roast(
    message: str,
    mode: RoastMode,
    personality: Personality,
    session: Session,
    library: Library,
    detected_intents: list[str],
    allow_general_fallback: bool = True,
) -> Optional[RoastTemplate]:
    """Pick the best roast template for this turn.

    Returns None only if both the mode pool and the general fallback are empty.
    """
    candidates = _build_candidates(
        mode=mode,
        personality=personality,
        library=library,
        detected_intents=detected_intents,
        recent=session.recent_roast_ids,
    )

    if not candidates and allow_general_fallback:
        candidates = _build_candidates(
            mode=RoastMode.GENERAL,
            personality=personality,
            library=library,
            detected_intents=detected_intents,
            recent=session.recent_roast_ids,
        )

    if not candidates:
        return None

    scored = [
        _score_roast(t, message, detected_intents, session.recent_roast_ids)
        for t in candidates
    ]
    chosen = _weighted_random(scored)
    return chosen.template


def _build_candidates(
    mode: RoastMode,
    personality: Personality,
    library: Library,
    detected_intents: list[str],
    recent: list[str],
) -> list[RoastTemplate]:
    pool = library.roasts_for_mode(mode)
    pdef = library.personalities.get(personality)

    out: list[RoastTemplate] = []
    for roast in pool:
        if roast.personalities and personality not in roast.personalities:
            continue
        if pdef and not (pdef.min_damage <= roast.damage <= pdef.max_damage):
            continue
        if pdef and mode.value in [m.value for m in pdef.blocked_modes]:
            continue
        if roast.intents and detected_intents:
            if not any(i in roast.intents for i in detected_intents):
                continue
        out.append(roast)
    return out


def _score_roast(
    template: RoastTemplate,
    message: str,
    detected_intents: list[str],
    recent: list[str],
) -> ScoredRoast:
    score = float(template.weight)
    reasons: list[str] = []

    msg_low = message.lower()

    # Keyword overlap
    if template.keywords:
        hits = sum(1 for kw in template.keywords if kw.lower() in msg_low)
        if hits:
            score += hits * 2
            reasons.append(f"keywords:{hits}")

    # Trigger phrase hit. Trigger phrases are an explicit "if the user said
    # THIS, deliver THAT" signal, so we apply a large bonus that effectively
    # makes the matched roast the deterministic winner. Otherwise a generic
    # savage roast at score 1.0 will out-compete the targeted roast 80%+ of
    # the time just by sheer numbers in the candidate pool.
    if template.trigger_phrases:
        phrases_hit = [p for p in template.trigger_phrases if p.lower() in msg_low]
        if phrases_hit:
            score += 100 * len(phrases_hit)
            reasons.append(f"phrases:{len(phrases_hit)}")

    # Intent match bonus. Intent detection is more reliable than keyword
    # overlap, so we apply a much larger bonus than the keyword/keyword+1 hit
    # (2x). 50x keeps intent-targeted roasts competitive against the ~25
    # generic savage roasts in the pool (each at score 1.0).
    if template.intents and detected_intents:
        if any(i in template.intents for i in detected_intents):
            score += 50
            reasons.append("intent:match")

    # Novelty penalty for recent roasts
    if template.id in recent:
        # The more recent, the bigger the penalty
        idx = recent[::-1].index(template.id)
        score -= 5 * (RECENT_ROAST_WINDOW - idx)
        reasons.append(f"recent:-{5 * (RECENT_ROAST_WINDOW - idx)}")

    return ScoredRoast(template=template, score=max(score, 0.1), reasons=reasons)


def _weighted_random(scored: list[ScoredRoast]) -> ScoredRoast:
    total = sum(s.score for s in scored)
    if total <= 0:
        return random.choice(scored)
    pick = random.uniform(0, total)
    cum = 0.0
    for s in scored:
        cum += s.score
        if pick <= cum:
            return s
    return scored[-1]


# ----- Special-purpose selections (openers, closers, comebacks) -----

def select_opener(
    mode: RoastMode, personality: Personality, library: Library
) -> Optional[object]:
    from .models import SpecialTemplate

    pool = library.openers
    candidates: list[SpecialTemplate] = []
    for o in pool:
        if o.personalities and personality not in o.personalities:
            continue
        if o.mode and o.mode != mode:
            continue
        candidates.append(o)
    if not candidates:
        return None
    return random.choice(candidates)


def select_closer(
    personality: Personality, library: Library
) -> Optional[object]:
    from .models import SpecialTemplate

    candidates: list[SpecialTemplate] = []
    for c in library.closers:
        if c.personalities and personality not in c.personalities:
            continue
        candidates.append(c)
    if not candidates:
        return None
    return random.choice(candidates)


def select_comeback(personality: Personality, library: Library) -> Optional[object]:
    from .models import SpecialTemplate

    candidates: list[SpecialTemplate] = []
    for c in library.comebacks:
        if c.personalities and personality not in c.personalities:
            continue
        candidates.append(c)
    if not candidates:
        return None
    return random.choice(candidates)


def select_callback(personality: Personality, library: Library) -> Optional[object]:
    from .models import SpecialTemplate

    candidates: list[SpecialTemplate] = []
    for c in library.callbacks:
        if c.personalities and personality not in c.personalities:
            continue
        candidates.append(c)
    if not candidates:
        return None
    return random.choice(candidates)


# ----- Personalization wrapper -----

def apply_personality_flavor(
    text: Optional[str], personality: Personality, library: Library
) -> Optional[str]:
    """Optionally prepend a prefix and append a suffix for flavor.

    Returns None if text is None (caller's signal that no roast was selected).
    All other None-like inputs are treated as the empty string.
    """
    if text is None:
        return None
    pdef = library.personalities.get(personality)
    if not pdef:
        return text
    out = text
    if pdef.prefixes and random.random() < 0.4:
        out = random.choice([p for p in pdef.prefixes if p]) + " " + out
    if pdef.suffixes and random.random() < 0.5:
        suffix = random.choice([s for s in pdef.suffixes if s])
        if suffix and not out.endswith(suffix):
            out = out + " " + suffix
    return out
