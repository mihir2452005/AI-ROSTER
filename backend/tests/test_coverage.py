"""Library coverage tests.

For every (mode, personality) combination, we assert that at least one roast
template is deliverable. The engine relies on this invariant: if a mode x
personality cell is empty, the user gets a stale 'I have nothing for you'
fallback for every turn.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.library import LIB
from app.models import Personality, RoastMode


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


def _is_deliverable(template, personality: Personality, mode: RoastMode) -> bool:
    """Replicate the matcher's filter rules to count this template as
    'deliverable' for the given (mode, personality) pair."""
    if template.personalities and personality not in template.personalities:
        return False
    pdef = LIB.personalities.get(personality)
    if pdef is None:
        return False
    if not (pdef.min_damage <= template.damage <= pdef.max_damage):
        return False
    if mode in pdef.blocked_modes:
        return False
    return True


def _is_blocked(personality: Personality, mode: RoastMode) -> bool:
    """Combinations the library explicitly blocks. These are by design and
    are excluded from the coverage test."""
    pdef = LIB.personalities.get(personality)
    if pdef is None:
        return True
    if mode in pdef.blocked_modes:
        return True
    if mode not in pdef.allowed_modes:
        return True
    return False


# ----- Full coverage matrix -----

@pytest.mark.parametrize("mode", list(RoastMode))
@pytest.mark.parametrize("personality", list(Personality))
def test_every_mode_personality_pair_has_at_least_one_roast(mode, personality):
    """For every (mode, personality) pair where the personality hasn't blocked
    the mode, we must have at least one deliverable roast. Combinations the
    library explicitly blocks are skipped by design."""
    if _is_blocked(personality, mode):
        pytest.skip(f"{personality.value} blocks {mode.value} by design")
    pool = LIB.roasts_for_mode(mode)
    deliverable = [t for t in pool if _is_deliverable(t, personality, mode)]
    assert deliverable, (
        f"no deliverable roasts for mode={mode.value} personality={personality.value}"
    )


# ----- Each personality has at least one general-mode roast -----

def test_general_mode_works_for_every_personality():
    pool = LIB.roasts_for_mode(RoastMode.GENERAL)
    for personality in Personality:
        deliverable = [t for t in pool if _is_deliverable(t, personality, RoastMode.GENERAL)]
        assert deliverable, f"general mode empty for {personality.value}"


# ----- Each personality has a personality-appropriate opener/closer/comeback -----

@pytest.mark.parametrize("personality", list(Personality))
def test_every_personality_has_an_opener(personality):
    candidates = [o for o in LIB.openers
                  if not o.personalities or personality in o.personalities]
    assert candidates, f"no opener available for {personality.value}"


@pytest.mark.parametrize("personality", list(Personality))
def test_every_personality_has_a_closer(personality):
    candidates = [c for c in LIB.closers
                  if not c.personalities or personality in c.personalities]
    assert candidates, f"no closer available for {personality.value}"


@pytest.mark.parametrize("personality", list(Personality))
def test_every_personality_has_a_comeback(personality):
    candidates = [c for c in LIB.comebacks
                  if not c.personalities or personality in c.personalities]
    assert candidates, f"no comeback available for {personality.value}"


# ----- Library-wide invariants -----

def test_no_roast_has_placeholder_mismatch():
    """Every {placeholder} token in a template must have a corresponding
    entry in the placeholders dict."""
    import re
    PH = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    for t in LIB.all_roasts():
        referenced = set(PH.findall(t.template))
        declared = set(t.placeholders.keys())
        missing = referenced - declared
        assert not missing, f"{t.id}: undeclared placeholders {missing}"


def test_no_roast_references_unknown_personality():
    for t in LIB.all_roasts():
        for p in t.personalities:
            assert p in LIB.personalities, f"{t.id}: unknown personality {p.value}"


def test_damage_within_personality_range_for_all_listings():
    for t in LIB.all_roasts():
        for p in t.personalities:
            pdef = LIB.personalities.get(p)
            if pdef is None:
                continue
            assert pdef.min_damage <= t.damage <= pdef.max_damage, (
                f"{t.id}: personality {p.value} range [{pdef.min_damage}-{pdef.max_damage}] "
                f"doesn't include damage {t.damage}"
            )


def test_no_roast_listed_in_blocked_mode():
    for t in LIB.all_roasts():
        for p in t.personalities:
            pdef = LIB.personalities.get(p)
            if pdef is None:
                continue
            assert t.mode not in pdef.blocked_modes, (
                f"{t.id}: personality {p.value} blocks mode {t.mode.value}"
            )
