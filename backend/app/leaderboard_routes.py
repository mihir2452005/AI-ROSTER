"""Public leaderboard endpoint - shows top users without requiring admin auth.

The admin leaderboard at /api/admin/leaderboard is the full version; this one
trims the response (no PII other than name/email prefix) and is safe to expose
to anonymous users.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import Depends

from . import db_models
from .database import get_db
from .sanitize import sanitize_text, mask_email

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


def _week_id(d: datetime) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _safe_display_name(raw: Optional[str]) -> str:
    """Cap length, strip control chars, and replace embedded URLs and
    HTML-ish brackets so a user with a malicious full_name can't poison
    the public leaderboard. We do not try to render any HTML — frontend
    renders the string as text.
    """
    s = sanitize_text(raw or "", max_length=64) or ""
    # Replace <, >, & with safe equivalents so a stray "<script>" doesn't
    # make it through to a downstream renderer that interprets HTML.
    s = s.replace("<", "‹").replace(">", "›")
    # Collapse http(s):// sequences — links don't belong in a name slot.
    s = re.sub(r"https?://\S+", "[link removed]", s)
    return s.strip() or "Anonymous"


@router.get("")
def public_leaderboard(
    period: str = Query("week", pattern="^(day|week|month|all)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Top users by total damage dealt.

    `period` controls the time window:
    - `day`:   last 24 hours
    - `week`:  last 7 days
    - `month`: last 30 days
    - `all`:   all time

    Uses a pre-computed `leaderboard_snapshots` row if one is fresh
    (<= 2 hours old) for the same (period, period_id) tuple. Otherwise
    falls back to live aggregation. The snapshot is populated by the
    background job in `app.jobs.snapshot_leaderboard`.
    """
    from datetime import datetime as _dt
    now = datetime.now(timezone.utc)
    if period == "day":
        period_id = now.strftime("%Y-%m-%d")
    elif period == "week":
        period_id = _week_id(now)
    elif period == "month":
        period_id = now.strftime("%Y-%m")
    else:
        period_id = "all"

    # Try snapshot first.
    fresh = (
        db.query(db_models.LeaderboardSnapshot)
        .filter(
            db_models.LeaderboardSnapshot.period == period,
            db_models.LeaderboardSnapshot.period_id == period_id,
            db_models.LeaderboardSnapshot.captured_at >= now - timedelta(hours=2),
        )
        .order_by(db_models.LeaderboardSnapshot.rank.asc())
        .limit(limit)
        .all()
    )
    if fresh:
        return {
            "period": period_id,
            "source": "snapshot",
            "entries": [
                {
                    "rank": r.rank,
                    "user_id": r.user_id,
                    "total_damage": float(r.total_damage or 0.0),
                    "message_count": int(r.message_count or 0),
                    "display_name": r.display_name,
                    "masked_email": r.masked_email,
                }
                for r in fresh
            ],
        }

    # Fallback: live aggregation.
    if period == "day":
        start = now - timedelta(days=1)
    elif period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        start = datetime(1970, 1, 1, tzinfo=timezone.utc)

    q = (
        db.query(
            db_models.ChatHistory.user_id,
            func.coalesce(func.sum(db_models.ChatHistory.score_total), 0.0).label("total_damage"),
            func.count(db_models.ChatHistory.id).label("message_count"),
        )
    )
    if period != "all":
        q = q.filter(db_models.ChatHistory.created_at >= start)
    rows = (
        q.group_by(db_models.ChatHistory.user_id)
        .order_by(func.sum(db_models.ChatHistory.score_total).desc())
        .limit(limit)
        .all()
    )

    entries = []
    for rank, (uid, dmg, count) in enumerate(rows, start=1):
        u = db.get(db_models.User, uid)
        if not u:
            continue
        # Only show first name + initial of email for privacy. Both
        # the full_name path and the email-fallback path go through
        # _safe_display_name so an attacker who registers with no name
        # and a malicious email local-part can't smuggle HTML into the
        # public leaderboard. See audit #19.
        if u.full_name:
            display_name = _safe_display_name(u.full_name)
        elif u.email and "@" in u.email:
            display_name = _safe_display_name(u.email.split("@")[0][:24])
        else:
            display_name = "Anonymous"
        masked_email = mask_email(u.email) if u.email else None
        entries.append({
            "rank": rank,
            "user_id": uid,
            "display_name": display_name,
            "masked_email": masked_email,
            "total_damage": float(dmg or 0),
            "message_count": int(count or 0),
        })

    return {"period": period_id, "entries": entries}
