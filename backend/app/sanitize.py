"""Defensive input sanitization.

The engine is fundamentally a string-in / string-out system, and a lot of
the user-supplied text gets persisted to a database that is later read by
admin dashboards or future client code. This module provides small,
side-effect-free helpers to:
  - cap string length to a configurable maximum
  - strip non-printable / non-tab / non-newline control characters that have
    no business in a chat transcript (e.g. ANSI escapes, NULL bytes)
  - cap repeat-newline runs so a single log line doesn't become a thousand
  - mask PII (email) consistently across all endpoints

This is NOT a general-purpose HTML/JS sanitizer. The frontend renders these
strings inside React (which auto-escapes), and we do not insert user input
into HTML attributes without explicit handling.
"""
from __future__ import annotations

import re

# Allow printable ASCII + extended Latin + common Unicode ranges, plus
# tab and newline. Reject everything in the C0 control block (0x00-0x1F)
# except \t (0x09), \n (0x0A), \r (0x0D), and the DEL (0x7F) char.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str | None, *, max_length: int) -> str | None:
    """Trim, strip control chars, collapse repeated newlines, and cap length.

    Returns None for None input. Empty strings are returned as empty.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    # Strip ASCII control chars (keep \n, \r, \t).
    value = _CONTROL_CHARS_RE.sub("", value)
    # Collapse 4+ consecutive newlines into 3 (UI cleanliness).
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    # Cap length. Truncating in the middle of a multi-byte char is fine;
    # the database column is utf-8 and we don't try to keep whole graphemes.
    if len(value) > max_length:
        value = value[:max_length]
    return value


def mask_email(email: str) -> str:
    """Mask the local part of an email to avoid leaking PII in API
    responses. e.g. alice@example.com -> al***@example.com.

    Always keeps the domain and the first two characters of the local
    part. Falls back to the original string if it doesn't look like
    an email. There is intentionally a single shared implementation
    used by both the public leaderboard and the admin endpoints so
    the two never drift apart.
    """
    if not email or "@" not in email:
        return email or ""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0] if local else '*'}***@{domain}"
    return f"{local[:2]}***@{domain}"

