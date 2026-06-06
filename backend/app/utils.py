"""Shared utilities used by the auth and account routes:
  * `email.py`             — token generation + email sending (SMTP / dev-log)
  * `audit.py`             — append rows to `audit_logs` for sensitive actions
  * `feature_flags.py`     — runtime-toggleable boolean flags with in-process cache
  * `achievements.py`      — achievement definitions and unlock logic
  * `soft_delete.py`       — soft-delete filter mixin / helpers
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import smtplib
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email tokens (verification + password reset)
# ---------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_email_token(
    db: Session, user_id: int, purpose: str, ttl_seconds: int,
) -> str:
    """Create a single-use token row and return the plaintext token.

    The plaintext is returned to the caller exactly ONCE (to embed
    in an email). The DB stores only the sha256 hash; a DB leak
    cannot be used to authenticate.

    Args:
        purpose: "verify" or "reset"
        ttl_seconds: lifetime, e.g. 86400 for verify, 3600 for reset
    """
    from . import db_models  # local import to dodge circular

    token = secrets.token_urlsafe(32)
    row = db_models.EmailToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=_hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    )
    db.add(row)
    db.commit()
    return token


def consume_email_token(
    db: Session, token: str, purpose: str,
) -> Optional["db_models.User"]:
    """Validate + consume a token. Returns the User on success, None
    on any failure (expired, used, wrong purpose, malformed).

    On success, the row is marked `used_at = now` and committed.
    """
    from . import db_models

    if not token or not isinstance(token, str):
        return None
    th = _hash_token(token)
    row = db.query(db_models.EmailToken).filter(
        db_models.EmailToken.token_hash == th,
        db_models.EmailToken.purpose == purpose,
    ).first()
    if row is None:
        return None
    if row.used_at is not None:
        return None
    if row.expires_at is None:
        return None
    # SQLite drops tzinfo on read; normalise both sides to aware UTC
    # before comparing.
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    user = db.get(db_models.User, row.user_id)
    if user is None:
        return None
    row.used_at = datetime.now(timezone.utc)
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Text sanitization
# ---------------------------------------------------------------------------
#
# Round 9 — used by the public contact form and the admin broadcast
# notification endpoint. Strips HTML tags, escapes remaining angle
# brackets, and caps the result to `max_len` characters. Catches the
# most common XSS smuggled through user-typed text on the way into
# the admin inbox or another user's notification feed.


_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_text(value: Optional[str], max_len: int = 1000) -> str:
    """Strip HTML, escape the rest, and cap length.

    The contact form, broadcast notification, and any other
    user-submitted free-text field should call this before persisting.
    Never raises — a None or non-string input becomes "".
    """
    if not value or not isinstance(value, str):
        return ""
    cleaned = _TAG_RE.sub("", value)
    cleaned = html.escape(cleaned, quote=False)
    cleaned = cleaned.strip()
    if max_len and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------


def _send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Falls back to log-only in dev.

    Configuration via env (all optional in dev):
        SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
    If SMTP_HOST is unset, the message is written to the application log
    and `dev_emails.log` so a developer can inspect the verification /
    reset link without a real mail server.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    from_addr = os.environ.get("SMTP_FROM", "no-reply@roastgpt.local")
    if not host:
        # Dev mode: log the body and append to dev_emails.log. The
        # body can contain non-ASCII (emojis, i18n) so we always
        # encode safely for the application log — without this, a
        # Windows cp1252 console would crash the worker mid-request.
        log.info(
            "DEV EMAIL to=%s subject=%s\n%s",
            to, subject, body,
        )
        try:
            with open("dev_emails.log", "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now(timezone.utc).isoformat()} ---\n")
                f.write(f"To: {to}\nSubject: {subject}\n{body}\n")
        except OSError:
            pass
        return

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USERNAME", "")
    pwd = os.environ.get("SMTP_PASSWORD", "")
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            if user:
                s.login(user, pwd)
            s.send_message(msg)
    except Exception as e:  # pragma: no cover - SMTP error path
        log.warning("SMTP send failed: %s", e)


def send_verification_email(to: str, token: str) -> None:
    """Compose the verification email with a `?token=...&uid=...` link.

    The link target comes from FRONTEND_URL (defaults to localhost:3000).
    """
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    link = f"{base}/verify-email?token={token}"
    _send_email(
        to=to,
        subject="Verify your RoastGPT email",
        body=(
            "Welcome to RoastGPT!\n\n"
            f"Click this link to verify your email and unlock all features:\n{link}\n\n"
            "The link is good for 24 hours. If you didn't sign up, ignore this email.\n"
        ),
    )


def send_password_reset_email(to: str, token: str) -> None:
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    link = f"{base}/reset-password?token={token}"
    _send_email(
        to=to,
        subject="Reset your RoastGPT password",
        body=(
            "Someone (hopefully you) asked to reset your password.\n\n"
            f"Click this link to set a new password:\n{link}\n\n"
            "The link is good for 1 hour. If you didn't request a reset, ignore this email\n"
            "and your password will stay the same.\n"
        ),
    )


def send_welcome_email(to: str, name: Optional[str] = None) -> None:
    """Sent on registration. The user is logged in already so this is
    a low-friction touchpoint, not a re-pitch."""
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    greeting = f"Hi {name}," if name else "Hi there,"
    _send_email(
        to=to,
        subject="Welcome to RoastGPT 🔥",
        body=(
            f"{greeting}\n\n"
            "Your account is ready. Pick a mode, pick a personality, and\n"
            "prepare to get roasted. The first 5 messages are free.\n\n"
            f"Start a session: {base}\n\n"
            "If you ever get stuck, the help center is one click away.\n"
            "\n— RoastGPT\n"
        ),
    )


def send_payment_success_email(
    to: str, plan_name: str, period_end_iso: Optional[str] = None
) -> None:
    """Sent on successful payment verification / webhook capture."""
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    until = ""
    if period_end_iso:
        until = f" Your subscription is active until {period_end_iso[:10]}."
    _send_email(
        to=to,
        subject=f"Payment received: {plan_name} ✅",
        body=(
            f"Thanks! Your {plan_name} subscription is now active.{until}\n\n"
            f"Manage your subscription: {base}/account\n"
            "\n— RoastGPT\n"
        ),
    )


def send_subscription_expiring_email(
    to: str, days_left: int, plan_name: str
) -> None:
    """Sent ~3 days before the period ends. In-app notification is the
    primary surface; the email is the catch-all for users who haven't
    opened the app in a while."""
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    _send_email(
        to=to,
        subject=f"Your {plan_name} subscription expires in {days_left} days",
        body=(
            f"Heads up: your {plan_name} subscription ends in {days_left} days.\n\n"
            f"Renew or change plan: {base}/pricing\n"
            "\n— RoastGPT\n"
        ),
    )


def send_subscription_cancelled_email(to: str, plan_name: str) -> None:
    """Sent when a user explicitly cancels."""
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    _send_email(
        to=to,
        subject=f"Your {plan_name} subscription has been cancelled",
        body=(
            f"Your {plan_name} subscription is cancelled. You'll keep access\n"
            "until the end of the current billing period, then revert to the\n"
            "free tier (5 messages per account).\n\n"
            f"Re-subscribe any time: {base}/pricing\n"
            "\n— RoastGPT\n"
        ),
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def log_action(
    db: Session,
    *,
    action: str,
    actor_user_id: Optional[int] = None,
    actor_ip: Optional[str] = None,
    target_user_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """Append a row to `audit_logs`. Best-effort; never raises."""
    from . import db_models

    try:
        row = db_models.AuditLog(
            action=action[:64],
            actor_user_id=actor_user_id,
            actor_ip=(actor_ip or "")[:64] or None,
            target_user_id=target_user_id,
            details_json=details,
        )
        db.add(row)
        db.commit()
    except Exception as e:  # pragma: no cover - DB error path
        log.warning("audit log write failed (%s): %s", action, e)
        try:
            db.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
#
# The cache now lives in `app.cache` (Redis with in-memory fallback).
# We still keep `_FLAG_CACHE_LOADED_AT` as a TTL marker so we re-load
# from the DB only every 60 seconds. set_flag() invalidates the key
# immediately, so a freshly-flipped flag is visible on the next read.


_FLAG_CACHE: dict[str, bool] = {}
_FLAG_CACHE_LOADED_AT: float = 0.0
_FLAG_CACHE_TTL = 60.0  # seconds


def is_flag_enabled(db: Session, key: str, default: bool = False) -> bool:
    """Read a feature flag, with a 60s in-process cache."""
    import time
    from . import cache as _cache

    global _FLAG_CACHE_LOADED_AT
    if not key:
        return default
    now = time.time()
    if (now - _FLAG_CACHE_LOADED_AT) > _FLAG_CACHE_TTL:
        _FLAG_CACHE.clear()
        _FLAG_CACHE_LOADED_AT = now
        try:
            from . import db_models
            for row in db.query(db_models.FeatureFlag).all():
                _FLAG_CACHE[row.key] = bool(row.enabled)
            # Best-effort: also write into the shared cache so other
            # processes / pods see the same answer.
            for k, v in _FLAG_CACHE.items():
                _cache.setex(f"flag:{k}", int(_FLAG_CACHE_TTL) + 5, "1" if v else "0")
        except Exception:  # pragma: no cover
            pass
    # If our local cache has it, return it. Otherwise ask the shared
    # cache (Redis when configured). Falls back to default on miss.
    if key in _FLAG_CACHE:
        return _FLAG_CACHE[key]
    cached = _cache.get(f"flag:{key}")
    if cached is not None:
        return cached == "1"
    return default


def set_flag(db: Session, key: str, enabled: bool, updated_by_id: Optional[int] = None,
             description: Optional[str] = None) -> None:
    """Upsert a flag and invalidate the cache."""
    from . import db_models, cache as _cache
    row = db.get(db_models.FeatureFlag, key)
    if row is None:
        row = db_models.FeatureFlag(key=key, enabled=enabled, description=description)
        db.add(row)
    else:
        row.enabled = enabled
        if description is not None:
            row.description = description
    if updated_by_id is not None:
        row.updated_by_id = updated_by_id
    db.commit()
    _FLAG_CACHE.pop(key, None)
    _FLAG_CACHE_LOADED_AT = 0.0
    # Invalidate the shared cache too. setex overwrites with a short
    # TTL so subsequent reads re-fetch from the DB on the next cycle.
    _cache.setex(f"flag:{key}", 5, "1" if enabled else "0")


def list_flags(db: Session) -> list[dict]:
    from . import db_models
    return [
        {
            "key": r.key,
            "enabled": bool(r.enabled),
            "description": r.description,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in db.query(db_models.FeatureFlag).order_by(db_models.FeatureFlag.key).all()
    ]


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


# Static catalog. Seeded into the DB by `app.jobs.seed_achievements()` at
# startup so they're editable without a code change.
ACHIEVEMENT_CATALOG: list[dict] = [
    {
        "key": "first_roast", "name": "First Burn", "emoji": "🔥",
        "description": "Sent your first roast.", "category": "starter",
        "rarity": "common", "points": 5, "sort_order": 10,
    },
    {
        "key": "ten_roasts", "name": "Warming Up", "emoji": "♨️",
        "description": "Sent 10 roasts.", "category": "milestone",
        "rarity": "common", "points": 10, "sort_order": 20,
    },
    {
        "key": "hundred_roasts", "name": "Centurion", "emoji": "💯",
        "description": "Sent 100 roasts.", "category": "milestone",
        "rarity": "rare", "points": 25, "sort_order": 30,
    },
    {
        "key": "thousand_roasts", "name": "Roastmaster", "emoji": "👑",
        "description": "Sent 1,000 roasts.", "category": "milestone",
        "rarity": "legendary", "points": 100, "sort_order": 40,
    },
    {
        "key": "savage_mode", "name": "Savage", "emoji": "😈",
        "description": "Tried the Savage mode.", "category": "explorer",
        "rarity": "common", "points": 5, "sort_order": 50,
    },
    {
        "key": "all_modes", "name": "Taste The Rainbow", "emoji": "🌈",
        "description": "Tried every roast mode.", "category": "explorer",
        "rarity": "rare", "points": 25, "sort_order": 60,
    },
    {
        "key": "first_share", "name": "Sharing Is Caring", "emoji": "🔗",
        "description": "Shared a roast conversation.", "category": "social",
        "rarity": "common", "points": 10, "sort_order": 70,
    },
    {
        "key": "first_sub", "name": "Premium Taste", "emoji": "⭐",
        "description": "Started your first paid subscription.", "category": "social",
        "rarity": "rare", "points": 25, "sort_order": 80,
    },
    {
        "key": "high_score", "name": "Damage Dealer", "emoji": "💥",
        "description": "Hit a single-message score of 90+.", "category": "skill",
        "rarity": "rare", "points": 20, "sort_order": 90,
    },
    {
        "key": "comeback_kid", "name": "Comeback Kid", "emoji": "🥊",
        "description": "Won 5 comeback exchanges.", "category": "skill",
        "rarity": "rare", "points": 20, "sort_order": 100,
    },
    {
        "key": "verified", "name": "Verified Human", "emoji": "✅",
        "description": "Verified your email.", "category": "starter",
        "rarity": "common", "points": 5, "sort_order": 110,
    },
    {
        "key": "avatar_set", "name": "Face Card", "emoji": "🖼️",
        "description": "Set a profile picture.", "category": "starter",
        "rarity": "common", "points": 5, "sort_order": 120,
    },
]


def seed_achievements(db: Session) -> int:
    """Idempotently insert the catalog. Returns the number of NEW rows."""
    from . import db_models
    inserted = 0
    for a in ACHIEVEMENT_CATALOG:
        existing = db.get(db_models.Achievement, a["key"])
        if existing is not None:
            continue
        db.add(db_models.Achievement(**a))
        inserted += 1
    if inserted:
        db.commit()
    return inserted


def unlock_achievement(db: Session, user_id: int, key: str) -> bool:
    """Unlock an achievement for a user. Returns True iff this call
    actually inserted a new row (False if already unlocked)."""
    from . import db_models
    # Verify the key exists in the catalog (defence — protects against
    # typos in caller code that would otherwise silently insert orphans).
    if db.get(db_models.Achievement, key) is None:
        return False
    existing = db.query(db_models.UserAchievement).filter(
        db_models.UserAchievement.user_id == user_id,
        db_models.UserAchievement.achievement_key == key,
    ).first()
    if existing is not None:
        return False
    db.add(db_models.UserAchievement(user_id=user_id, achievement_key=key))
    db.commit()
    return True


def unlock_achievements_for_user(
    db: Session, user_id: int, *, total_messages: int,
    mode_counts: dict, personality_counts: dict, score_total: float,
    has_subscription: bool, has_shared: bool, has_verified: bool,
    has_avatar: bool, high_score: float = 0.0, comeback_wins: int = 0,
) -> list[str]:
    """Evaluate every achievement condition and unlock the ones that
    match. Returns the list of newly-unlocked keys (in catalog order)."""
    unlocked: list[str] = []
    if total_messages >= 1 and unlock_achievement(db, user_id, "first_roast"):
        unlocked.append("first_roast")
    if total_messages >= 10 and unlock_achievement(db, user_id, "ten_roasts"):
        unlocked.append("ten_roasts")
    if total_messages >= 100 and unlock_achievement(db, user_id, "hundred_roasts"):
        unlocked.append("hundred_roasts")
    if total_messages >= 1000 and unlock_achievement(db, user_id, "thousand_roasts"):
        unlocked.append("thousand_roasts")
    if mode_counts.get("savage", 0) >= 1 and unlock_achievement(db, user_id, "savage_mode"):
        unlocked.append("savage_mode")
    if len([k for k, v in mode_counts.items() if v >= 1]) >= 8 and unlock_achievement(db, user_id, "all_modes"):
        unlocked.append("all_modes")
    if has_subscription and unlock_achievement(db, user_id, "first_sub"):
        unlocked.append("first_sub")
    if has_shared and unlock_achievement(db, user_id, "first_share"):
        unlocked.append("first_share")
    if high_score >= 90 and unlock_achievement(db, user_id, "high_score"):
        unlocked.append("high_score")
    if comeback_wins >= 5 and unlock_achievement(db, user_id, "comeback_kid"):
        unlocked.append("comeback_kid")
    if has_verified and unlock_achievement(db, user_id, "verified"):
        unlocked.append("verified")
    if has_avatar and unlock_achievement(db, user_id, "avatar_set"):
        unlocked.append("avatar_set")
    return unlocked


# ---------------------------------------------------------------------------
# Soft-delete helpers
# ---------------------------------------------------------------------------


def active_user_query(db: Session):
    """Build a `SELECT * FROM users WHERE deleted_at IS NULL` base query."""
    from . import db_models
    return db.query(db_models.User).filter(db_models.User.deleted_at.is_(None))
