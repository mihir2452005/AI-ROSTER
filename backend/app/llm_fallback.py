"""LLM fallback layer.

Used when the deterministic roast library has no good match
(`matcher.select_roast` returns None, OR the chosen template's score
is below `LLM_FALLBACK_SCORE_THRESHOLD`). The fallback calls a
chat-completion model to generate a roast in-character.

Provider support (pluggable via env var):
  - openai    — gpt-4o-mini by default, OPENAI_API_KEY required
  - anthropic — claude-3-5-haiku by default, ANTHROPIC_API_KEY required
  - stub      — always returns a fixed string. The default in dev so
                tests don't require network access.

A circuit breaker (LLM_MAX_FAILURES in 60s) blocks LLM calls after
a burst of failures, so a provider outage doesn't tie up request
workers waiting on a 30s timeout. Best-effort — if the call fails
or the breaker is open, we fall through to a static fallback.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)


# ----- Configuration -----

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "stub").lower()
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MAX_FAILURES = int(os.environ.get("LLM_MAX_FAILURES", "5"))
LLM_FAILURE_WINDOW = int(os.environ.get("LLM_FAILURE_WINDOW", "60"))
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "10"))
LLM_FALLBACK_SCORE_THRESHOLD = float(
    os.environ.get("LLM_FALLBACK_SCORE_THRESHOLD", "0.5")
)


# ----- Circuit breaker (in-process) -----

_failures: list[float] = []


def _record_failure() -> None:
    now = time.time()
    _failures.append(now)
    # Prune the window.
    cutoff = now - LLM_FAILURE_WINDOW
    while _failures and _failures[0] < cutoff:
        _failures.pop(0)


def _breaker_open() -> bool:
    if not _failures:
        return False
    cutoff = time.time() - LLM_FAILURE_WINDOW
    recent = [t for t in _failures if t >= cutoff]
    return len(recent) >= LLM_MAX_FAILURES


def breaker_status() -> dict:
    cutoff = time.time() - LLM_FAILURE_WINDOW
    recent = [t for t in _failures if t >= cutoff]
    return {
        "open": len(recent) >= LLM_MAX_FAILURES,
        "failures_in_window": len(recent),
        "max_failures": LLM_MAX_FAILURES,
        "window_seconds": LLM_FAILURE_WINDOW,
    }


# ----- Public entry point -----


def should_fallback(score: float) -> bool:
    """Return True iff the score is low enough to warrant an LLM call.

    The threshold is configurable; setting it to 0 disables the
    score-based fallback (only used when the library returns None).
    """
    if _breaker_open():
        return False
    if not LLM_PROVIDER or LLM_PROVIDER == "stub":
        return False  # stub doesn't talk to a real LLM
    return score < LLM_FALLBACK_SCORE_THRESHOLD


def generate_roast(
    *,
    message: str,
    mode: str,
    personality: str,
    user_name: Optional[str] = None,
    roaster_gender: Optional[str] = None,
) -> Optional[str]:
    """Call the configured LLM to generate a roast.

    Returns None on any failure or when the breaker is open. The
    caller is expected to fall back to a static string.
    """
    if _breaker_open():
        return None
    if not LLM_PROVIDER or LLM_PROVIDER == "stub":
        return None
    if not LLM_API_KEY:
        log.debug("LLM_API_KEY not set; skipping fallback")
        return None

    system = (
        f"You are a {personality} roaster in {mode} mode. "
        f"You speak to the user{' named ' + user_name if user_name else ''} "
        f"in {'masculine' if roaster_gender == 'male' else 'feminine' if roaster_gender == 'female' else 'neutral'} voice. "
        "Reply with a single short roast (1-2 sentences, < 240 chars). "
        "No moralizing. No 'as an AI'. No quotes around the reply."
    )
    user = message[:1000]

    try:
        if LLM_PROVIDER == "openai":
            return _call_openai(system, user)
        elif LLM_PROVIDER == "anthropic":
            return _call_anthropic(system, user)
        else:
            log.warning("unknown LLM_PROVIDER %r", LLM_PROVIDER)
            return None
    except Exception as e:
        _record_failure()
        log.warning("LLM fallback failed (%s): %s", LLM_PROVIDER, e)
        return None


# ----- Provider implementations -----


def _call_openai(system: str, user: str) -> Optional[str]:
    """OpenAI Chat Completions API. Stdlib only (urllib), no extra dep."""
    import json
    import urllib.request
    import urllib.error

    model = LLM_MODEL or "gpt-4o-mini"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 120,
        "temperature": 0.9,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip() or None


def _call_anthropic(system: str, user: str) -> Optional[str]:
    """Anthropic Messages API. Stdlib only."""
    import json
    import urllib.request

    model = LLM_MODEL or "claude-3-5-haiku-latest"
    payload = {
        "model": model,
        "max_tokens": 120,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": LLM_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    parts = body.get("content") or []
    text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    out = "".join(text_parts).strip()
    return out or None
