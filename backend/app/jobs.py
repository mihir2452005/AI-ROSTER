"""Periodic background jobs (in-process scheduler).

The free-tier Render deployment cannot run a long-lived worker
process, so jobs run inside the FastAPI lifespan handler using
`threading` + a simple tick loop. This is sufficient for the
workload (leaderboard snapshot every hour, retention sweep every
6 hours, achievements/already-immediate-on-write).

If you ever migrate to a worker dyno, swap `start_scheduler` to
spin up APScheduler/celery; the public functions are stable.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()


def start_scheduler() -> None:
    """Start the in-process job thread. Idempotent."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    if os.environ.get("DISABLE_BACKGROUND_JOBS", "").lower() in ("1", "true"):
        log.info("background jobs disabled via DISABLE_BACKGROUND_JOBS")
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(
        target=_run_loop, name="roastgpt-jobs", daemon=True,
    )
    _scheduler_thread.start()
    log.info("background jobs scheduler started")


def stop_scheduler() -> None:
    _scheduler_stop.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=2)


def _run_loop() -> None:
    """Tick every 60s, run jobs whose cadence has elapsed."""
    last_snapshot: dict[str, datetime] = {}
    last_retention: Optional[datetime] = None
    last_achievements_seed: Optional[datetime] = None
    # Short first-tick delay so the app finishes starting up.
    time.sleep(5)
    while not _scheduler_stop.is_set():
        try:
            from .database import SessionLocal
            from . import db_models
            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                # Leaderboard snapshot — every 60 minutes
                for period, period_id in _current_period_ids(now):
                    last = last_snapshot.get(period + ":" + period_id)
                    if last is None or (now - last) > timedelta(hours=1):
                        _snapshot_one(db, period, period_id)
                        last_snapshot[period + ":" + period_id] = now
                # Downgrade executor — every 15 minutes
                _process_scheduled_downgrades(db)
                # Retention sweep — every 6 hours
                if (last_retention is None
                        or (now - last_retention) > timedelta(hours=6)):
                    _retention_sweep(db)
                    last_retention = now
                # Achievements seed — once per process
                if last_achievements_seed is None:
                    from . import utils
                    utils.seed_achievements(db)
                    last_achievements_seed = now
            finally:
                db.close()
        except Exception as e:  # pragma: no cover
            log.warning("background job tick failed: %s", e)
        # Wait 60s or until stop.
        _scheduler_stop.wait(timeout=60)


def _current_period_ids(now: datetime) -> list[tuple[str, str]]:
    iso = now.isocalendar()
    week_id = f"{iso.year}-W{iso.week:02d}"
    month_id = now.strftime("%Y-%m")
    day_id = now.strftime("%Y-%m-%d")
    return [("day", day_id), ("week", week_id), ("month", month_id), ("all", "all")]


def _snapshot_one(db: Session, period: str, period_id: str) -> None:
    from . import db_models
    if period == "day":
        start = datetime.now(timezone.utc) - timedelta(days=1)
    elif period == "week":
        start = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        start = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    q = (
        db.query(
            db_models.ChatHistory.user_id,
            sqlfunc.coalesce(
                sqlfunc.sum(db_models.ChatHistory.score_total), 0.0
            ).label("total_damage"),
            sqlfunc.count(db_models.ChatHistory.id).label("message_count"),
        )
    )
    if period != "all":
        q = q.filter(db_models.ChatHistory.created_at >= start)
    rows = (
        q.group_by(db_models.ChatHistory.user_id)
        .order_by(sqlfunc.sum(db_models.ChatHistory.score_total).desc())
        .limit(50)
        .all()
    )
    # Wipe-and-replace for this (period, period_id) tuple.
    db.query(db_models.LeaderboardSnapshot).filter(
        db_models.LeaderboardSnapshot.period == period,
        db_models.LeaderboardSnapshot.period_id == period_id,
    ).delete()
    for rank, (uid, dmg, count) in enumerate(rows, start=1):
        db.add(db_models.LeaderboardSnapshot(
            period=period, period_id=period_id, rank=rank,
            user_id=uid, total_damage=float(dmg or 0),
            message_count=int(count or 0),
        ))
    db.commit()
    log.info("snapshot: %s/%s -> %d rows", period, period_id, len(rows))


def _retention_sweep(db: Session) -> None:
    """Hard-delete soft-deleted users past the 30-day window and
    anonymise their PII before the row goes away.

    Anonymisation runs first so that audit logs and any other tables
    that survive the cascade still reference a stable, opaque ID and
    cannot reconstruct the user from leftover text columns.
    """
    from . import db_models, utils
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale = db.query(db_models.User).filter(
        db_models.User.deleted_at.isnot(None),
        db_models.User.deleted_at < cutoff,
    ).all()
    for u in stale:
        # Anonymise the row's own PII columns first. Email is the
        # primary key most external systems key off, so we set it to a
        # deterministic, irreversible tombstone that still lets us
        # correlate the audit log entry.
        tombstone_id = f"deleted-{u.id}-{int(u.deleted_at.timestamp())}"
        u.email = tombstone_id + "@deleted.local"
        u.full_name = None
        u.hashed_password = ""  # bcrypt blobs are large; free them
        u.avatar_url = None
        u.last_login_ip = None
        u.favorite_mode = None
        u.favorite_personality = None
        u.recent_topics_json = None
        # Wipe denormalised caches on the linked memory row (cascade
        # would drop it, but we want the anonymisation to be visible in
        # any backup taken between here and the delete).
        if u.memory is not None:
            u.memory.recent_topics_json = None
        utils.log_action(
            db, action="account_hard_deleted",
            actor_user_id=None, target_user_id=u.id,
            details={"reason": "30d retention"},
        )
        # Cascade deletes in db_models.py handle subscriptions,
        # payments, chat_history, roast_sessions, memory. The
        # audit_logs target_user_id is SET NULL, so they survive.
        db.delete(u)
    if stale:
        db.commit()
        log.info("retention: hard-deleted %d users", len(stale))


def _process_scheduled_downgrades(db: Session) -> None:
    """Execute scheduled downgrades whose period has ended.

    `POST /api/subscriptions/downgrade` sets `scheduled_plan_id` and
    `cancel_at_period_end=True` on the active subscription. When the
    current period has elapsed, this job swaps the plan and writes an
    audit row. Re-issuing a fresh period for the new plan keeps the
    user in continuous service; the cancel_at_period_end flag is
    cleared so they stay subscribed going forward.
    """
    from . import db_models, utils
    now = datetime.now(timezone.utc)
    ready = (
        db.query(db_models.Subscription)
        .filter(
            db_models.Subscription.status == db_models.SubStatus.active,
            db_models.Subscription.scheduled_plan_id.isnot(None),
            db_models.Subscription.cancel_at_period_end.is_(True),
            db_models.Subscription.current_period_end.isnot(None),
        )
        .all()
    )
    swapped = 0
    for sub in ready:
        end = sub.current_period_end
        if end is None:
            continue
        # SQLite drops tzinfo on read; treat naive as UTC.
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end > now:
            continue
        target = db.get(db_models.SubscriptionPlan, sub.scheduled_plan_id)
        if target is None or not target.is_active:
            # Target plan gone — leave the sub alone and clear the
            # scheduled swap so we don't retry forever.
            sub.scheduled_plan_id = None
            sub.cancel_at_period_end = False
            continue
        old_plan_id = sub.plan_id
        sub.plan_id = target.id
        sub.scheduled_plan_id = None
        sub.cancel_at_period_end = False
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=target.duration_days)
        utils.log_action(
            db, action="subscription_downgrade_processed",
            actor_user_id=sub.user_id, target_user_id=sub.user_id,
            details={
                "from_plan_id": old_plan_id,
                "to_plan_id": target.id,
                "to_plan_code": target.plan_code,
            },
        )
        swapped += 1
    if swapped:
        db.commit()
        log.info("downgrade: swapped %d subscriptions", swapped)

