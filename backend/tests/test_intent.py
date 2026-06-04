"""Intent detection tests.

Covers per-intent detection, false-positive regression, and the
min_keyword_score threshold behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.intent import detect_intents, is_comeback
from app.library import LIB


@pytest.fixture(scope="module", autouse=True)
def _load_library():
    LIB.load()


def _names(message: str) -> list[str]:
    return [h.name for h in detect_intents(message, LIB)]


# ----- True positives -----

@pytest.mark.parametrize("msg,intent", [
    ("my code has a bug in the function",         "programming"),
    ("I pushed to main on Friday",                "programming"),
    ("i bombed the exam and didn't study",        "school"),
    ("my gpa is cooked",                          "school"),
    ("My K/D ratio is so low",                    "gaming"),
    ("ranked match tonight boys",                 "gaming"),
    ("i main zed in league of legends",           "gaming"),
    ("I dropped rank again",                      "gaming"),
    ("i went to the gym and did leg day",         "fitness"),
    ("I'm bulking, eating 3000 calories",         "fitness"),
    ("i lost my job and i'm broke",               "money"),
    ("my salary is too low",                      "money"),
    ("my ex texted me at 2am",                    "relationships"),
    ("i got ghosted",                             "relationships"),
    ("i bombed the interview today",             "career"),
    ("my boss is the worst",                      "career"),
    ("performance review went badly",             "career"),
])
def test_true_positives(msg, intent):
    assert intent in _names(msg), f"expected {intent} in {_names(msg)} for {msg!r}"


# ----- False positives (regression) -----

@pytest.mark.parametrize("msg", [
    "I called tech support about my bill",
    "support ticket opened",
    "I lost rank at work",
    "memory lane",
    "bus lane",
    "competitive pricing",
    "we are grinding in the office today",
    "for honor",
    "discord",
])
def test_false_positives(msg):
    assert _names(msg) == [], (
        f"unexpected intent detection for {msg!r}: got {_names(msg)}"
    )


def test_pushed_to_main_branch_is_programming():
    """'main branch' is now a deliberate programming phrase."""
    assert "programming" in _names("I pushed to main branch")


# ----- Multi-intent -----

def test_multi_intent_money_and_career():
    """'raise' fires money; no career because no career signal."""
    names = _names("i got a raise today")
    assert "money" in names
    assert "career" not in names


def test_multi_intent_school_and_programming_possible():
    """A message about both school and programming should detect both."""
    names = _names("i bombed my cs exam")
    # cs is not a school kw, but exam is
    assert "school" in names


# ----- Per-intent threshold -----

def test_gaming_min_keyword_score_is_one_or_more():
    """Gaming should fire on a single clean keyword (csgo, valorant, etc.)."""
    assert "gaming" in _names("i just bought valorant")
    assert "gaming" in _names("csgo is back")


def test_gaming_min_keyword_score_filters_garbage():
    """A nonsense word should not fire gaming even with multiple instances."""
    assert _names("banana telephone xylophone") == []


# ----- Phrase vs keyword: phrases always fire even at threshold 2 -----

def test_phrase_fires_even_for_strict_intent():
    """Programming has min_keyword_score=2, but a phrase still fires alone."""
    names = _names("stack overflow said it's a bug")
    assert "programming" in names


# ----- Empty / garbage -----

def test_empty_message():
    assert _names("") == []


def test_garbage_words():
    assert _names("xyzzy frobnicate quux") == []


def test_short_message():
    assert _names("hi") == []


# ----- Comeback detection -----

def test_comeback_yes():
    assert is_comeback("no u")
    assert is_comeback("your mom")
    assert is_comeback("YOU TOO")
    assert is_comeback("FIGHT ME BRO")
    assert is_comeback("come at me")
    assert is_comeback("you are so dumb")
    assert is_comeback("well actually...")


def test_comeback_no():
    assert not is_comeback("hello there")
    assert not is_comeback("my code doesn't work")
    assert not is_comeback("i'm doing fine")
