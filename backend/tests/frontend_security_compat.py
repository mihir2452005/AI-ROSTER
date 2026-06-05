"""Mirror of `frontend/lib/security.ts` for backend tests.

The frontend module is the actual defense; this is a faithful
port so backend tests can verify the same logic without spinning
up a Next.js build. The two implementations MUST stay in sync —
if you change one, change the other.

Why this exists: open-redirect vulnerabilities via `?return=`
need to be blocked at BOTH ends. The backend has no business
echoing a return path it doesn't own; the frontend is the
last line of defense against an attacker who manages to
inject a `?return=` directly into the URL.
"""
from __future__ import annotations


def is_safe_return_path(p) -> bool:
    if not isinstance(p, str):
        return False
    if len(p) == 0 or len(p) > 512:
        return False
    if not p.startswith("/"):
        return False
    # Reject protocol-relative URLs: //evil.com
    if p.startswith("//") or p.startswith("/\\"):
        return False
    # Reject any backslash anywhere (Windows path separator or
    # unicode tricks).
    if "\\" in p:
        return False
    # Reject scheme prefixes at the first segment.
    # e.g. /javascript:foo, /data:text/html
    first = p.lstrip("/").split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if ":" in first:
        return False
    return True


def safeReturnPath(p, fallback: str = "/") -> str:
    return p if is_safe_return_path(p) else fallback
