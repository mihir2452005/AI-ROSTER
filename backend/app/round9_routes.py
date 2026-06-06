"""Round 9 routes: contact form, notifications, system endpoints.

* `/api/v1/contact` (POST) — public; stores a message in
  `contact_messages`. Rate-limited like other public endpoints.
* `/api/v1/admin/contact-messages` (GET) — admin-only listing.
* `/api/v1/notifications` (GET) — current user's notifications
  (latest first, paginated). Marked-as-read endpoint to clear the
  badge counter.
* `/api/v1/admin/notifications/broadcast` (POST) — admin sends a
  notification to a single user or all users (used for admin
  announcements).
* `/api/v1/system/status` (GET) — public system status (db, cache,
  queue, sentry, version). Powers the public /status page and the
  admin monitoring dashboard.
* `/api/v1/system/metrics` (GET) — Prometheus text format, public
  (rate-limited). Used by the monitoring dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .auth import get_current_user, require_admin
from .database import get_db
from .db_models import ContactMessage, Notification, User
from . import monitoring, utils

log = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=5000)


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    created_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    body: str
    link: Optional[str] = None
    is_read: bool
    created_at: datetime


class NotificationList(BaseModel):
    items: List[NotificationOut]
    total: int
    unread_count: int


class MarkReadRequest(BaseModel):
    ids: List[int]


class MarkReadResponse(BaseModel):
    updated: int


class BroadcastRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=1000)
    link: Optional[str] = Field(default=None, max_length=500)
    # "all" | a single user_id
    target: str = "all"
    kind: str = "admin_announcement"


class SystemStatus(BaseModel):
    status: str
    database: str
    redis: str
    queue: str
    sentry: str
    version: str
    uptime_seconds: float
    maintenance_mode: bool
    build_sha: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================


def _client_ip(request: Request) -> Optional[str]:
    """Best-effort client IP. Mirrors main.py's trust model: the
    `X-Forwarded-For` header is only honoured if `TRUSTED_PROXIES` is
    configured. We don't import the global helper here to keep this
    router self-contained and easy to test."""
    return request.client.host if request.client else None


# =============================================================================
# Contact form
# =============================================================================


@router.post(
    "/contact",
    response_model=ContactResponse,
    status_code=201,
    summary="Submit a contact-form message",
)
def submit_contact(
    payload: ContactRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ContactResponse:
    """Public endpoint. Stores the message in `contact_messages` and
    returns the id. No auth required — the form is the entry point
    for prospects. Rate-limited at 10/hr per IP via the global
    middleware override on `/api/contact`."""
    # Run the same XSS scrubbing we apply everywhere else so a
    # contact-message body can't smuggle HTML into the admin inbox.
    from .utils import sanitize_text
    clean = {
        "name": sanitize_text(payload.name, 100),
        "subject": sanitize_text(payload.subject, 200),
        "message": sanitize_text(payload.message, 5000),
    }
    row = ContactMessage(
        name=clean["name"],
        email=str(payload.email).lower().strip(),
        subject=clean["subject"],
        message=clean["message"],
        ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:500],
        status="new",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("contact message %s from %s", row.id, row.email)
    return ContactResponse.model_validate(row)


@router.get(
    "/admin/contact-messages",
    response_model=dict,
    summary="List contact-form messages (admin)",
)
def list_contact_messages(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Optional[str] = Query(default=None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    q = db.query(ContactMessage)
    if status_filter:
        q = q.filter(ContactMessage.status == status_filter)
    total = q.count()
    rows = q.order_by(desc(ContactMessage.created_at)).offset(skip).limit(limit).all()
    return {
        "messages": [
            {
                "id": m.id,
                "name": m.name,
                "email": m.email,
                "subject": m.subject,
                "message": m.message,
                "status": m.status,
                "ip": m.ip,
                "created_at": m.created_at,
            }
            for m in rows
        ],
        "total": total,
    }


@router.patch(
    "/admin/contact-messages/{message_id}",
    response_model=dict,
    summary="Update a contact message's status (admin)",
)
def update_contact_message(
    message_id: int,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    status: str = Query(...),
) -> dict:
    if status not in ("new", "in_progress", "closed", "spam"):
        raise HTTPException(400, "status must be one of: new, in_progress, closed, spam")
    row = db.query(ContactMessage).filter(ContactMessage.id == message_id).one_or_none()
    if row is None:
        raise HTTPException(404, "message not found")
    row.status = status
    db.commit()
    return {"message": "updated", "id": message_id, "status": status}


# =============================================================================
# Notifications
# =============================================================================


def _create_notification(
    db: Session, user_id: int, kind: str, title: str, body: str, link: Optional[str] = None
) -> Notification:
    n = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.get(
    "/notifications",
    response_model=NotificationList,
    summary="List the current user's notifications",
)
def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(default=False),
) -> NotificationList:
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    total = q.count()
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .scalar()
        or 0
    )
    rows = (
        q.order_by(desc(Notification.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return NotificationList(
        items=[NotificationOut.model_validate(r) for r in rows],
        total=total,
        unread_count=int(unread_count),
    )


@router.post(
    "/notifications/mark-read",
    response_model=MarkReadResponse,
    summary="Mark notifications as read",
)
def mark_notifications_read(
    payload: MarkReadRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MarkReadResponse:
    if not payload.ids:
        return MarkReadResponse(updated=0)
    # `ids` is the list of notification ids the user clicked. We
    # scope the update to notifications owned by THIS user so a
    # bad client can't mark someone else's notifications read.
    updated = (
        db.query(Notification)
        .filter(
            Notification.id.in_(payload.ids),
            Notification.user_id == user.id,
        )
        .update({"is_read": True}, synchronize_session=False)
    )
    db.commit()
    return MarkReadResponse(updated=int(updated))


@router.post(
    "/notifications/mark-all-read",
    response_model=MarkReadResponse,
    summary="Mark ALL of the current user's notifications as read",
)
def mark_all_notifications_read(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MarkReadResponse:
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .update({"is_read": True}, synchronize_session=False)
    )
    db.commit()
    return MarkReadResponse(updated=int(updated))


@router.post(
    "/admin/notifications/broadcast",
    response_model=dict,
    status_code=201,
    summary="Broadcast a notification to one user or all (admin)",
)
def admin_broadcast_notification(
    payload: BroadcastRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from .utils import sanitize_text
    title = sanitize_text(payload.title, 200)
    body = sanitize_text(payload.body, 1000)

    if payload.target == "all":
        # Fan-out to all non-deleted, non-banned users. For a free-tier
        # service this is at most a few thousand rows; we chunk at 500
        # to avoid a single huge INSERT.
        users = (
            db.query(User.id)
            .filter(User.deleted_at.is_(None))
            .filter(User.is_banned.is_(False))
            .yield_per(500)
        )
        count = 0
        for (uid,) in users:
            db.add(Notification(
                user_id=uid,
                kind=payload.kind,
                title=title,
                body=body,
                link=payload.link,
            ))
            count += 1
        db.commit()
        return {"delivered_to": count, "kind": payload.kind}
    else:
        try:
            uid = int(payload.target)
        except ValueError:
            raise HTTPException(400, "target must be 'all' or a numeric user_id")
        u = db.query(User).filter(User.id == uid, User.deleted_at.is_(None), User.is_banned.is_(False)).one_or_none()
        if u is None:
            raise HTTPException(404, "user not found")
        n = _create_notification(db, uid, payload.kind, title, body, payload.link)
        return {"delivered_to": 1, "id": n.id, "kind": payload.kind}


# =============================================================================
# User activity (Account page → Recent Activity)
# =============================================================================


# Map raw audit-log actions to user-facing labels. Anything not in
# this map still shows up, but with the raw action string as the
# label. Kept narrow on purpose — most server-side audit events
# (admin actions, system events) are NOT user-relevant.
_ACTIVITY_LABELS: dict[str, str] = {
    "user_login": "Logged in",
    "user_logout": "Logged out",
    "user_logout_all": "Signed out of all sessions",
    "password_change": "Changed password",
    "password_reset_request": "Requested password reset",
    "password_reset_complete": "Reset password",
    "email_verification_request": "Requested email verification",
    "email_verified": "Verified email",
    "profile_update": "Updated profile",
    "avatar_upload": "Updated avatar",
    "account_delete": "Deleted account",
    "subscription_created": "Started a subscription",
    "subscription_upgraded": "Upgraded plan",
    "subscription_downgraded": "Downgraded plan",
    "subscription_cancelled": "Cancelled subscription",
    "payment_captured": "Payment received",
    "payment_failed": "Payment failed",
    "share_created": "Created a share link",
    "share_revoked": "Revoked a share link",
    "free_tier_exhausted": "Hit the free-tier limit",
    "first_share": "Earned the First Share achievement",
    "first_roast": "Earned the First Roast achievement",
}


class ActivityItem(BaseModel):
    id: int
    action: str
    label: str
    icon: str
    created_at: datetime
    details: Optional[dict] = None


class ActivityList(BaseModel):
    items: List[ActivityItem]
    total: int


# Friendly icons for the activity feed. Frontend can also override
# by `kind`, so this is just a sensible default.
_ACTIVITY_ICONS: dict[str, str] = {
    "user_login": "🔓",
    "user_logout": "🔒",
    "user_logout_all": "🔒",
    "password_change": "🔑",
    "password_reset_request": "🔑",
    "password_reset_complete": "🔑",
    "email_verification_request": "📧",
    "email_verified": "✅",
    "profile_update": "👤",
    "avatar_upload": "🖼️",
    "account_delete": "🗑️",
    "subscription_created": "💳",
    "subscription_upgraded": "⬆️",
    "subscription_downgraded": "⬇️",
    "subscription_cancelled": "⛔",
    "payment_captured": "✅",
    "payment_failed": "❌",
    "share_created": "🔗",
    "share_revoked": "🚫",
    "free_tier_exhausted": "🚧",
    "first_share": "🏆",
    "first_roast": "🏆",
}


@router.get(
    "/auth/me/activity",
    response_model=ActivityList,
    summary="Recent Activity for the Account page",
)
def my_activity(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> ActivityList:
    """Return the last N events the user triggered. We pull from
    `audit_logs` where the actor is the calling user — the same
    table that powers the admin audit-logs tab.

    Admin actions targeting the user (e.g. `admin_ban_user` where
    `target_user_id = me.id`) are NOT included; this is the user's
    OWN activity timeline, not their full history.
    """
    from .db_models import AuditLog
    q = db.query(AuditLog).filter(AuditLog.actor_user_id == user.id)
    total = q.count()
    rows = (
        q.order_by(desc(AuditLog.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    items: List[ActivityItem] = []
    for r in rows:
        items.append(ActivityItem(
            id=r.id,
            action=r.action,
            label=_ACTIVITY_LABELS.get(r.action, r.action.replace("_", " ").title()),
            icon=_ACTIVITY_ICONS.get(r.action, "•"),
            created_at=r.created_at,
            details=r.details_json,
        ))
    return ActivityList(items=items, total=total)


# =============================================================================
# System: health / metrics / status
# =============================================================================


# Module-level uptime — set when the module is imported. The value is
# the number of seconds since the process started. Used by the
# /system/status endpoint and the Prometheus text exposition.
import time as _time
_BOOT_TIME = _time.time()
_BUILD_VERSION = "1.4.0"  # Marketing/build label surfaced in /system/status.
# Falls back to FastAPI app.version ("0.1.0" in main.py) if main hasn't
# been imported yet (e.g. during unit tests that import round9_routes
# in isolation).
_BUILD_SHA: Optional[str] = None
try:
    import os
    _BUILD_SHA = os.environ.get("BUILD_SHA") or os.environ.get("GIT_SHA") or None
except Exception:
    _BUILD_SHA = None


def _check_database(db: Session) -> str:
    try:
        db.execute(select(1))
        return "ok"
    except Exception as e:
        log.warning("health: db check failed: %s", e)
        return "down"


def _check_redis() -> str:
    try:
        from . import cache
        if cache.is_redis():
            return "ok"
        return "memory"  # in-process fallback
    except Exception as e:
        log.warning("health: redis check failed: %s", e)
        return "down"


def _check_queue() -> str:
    try:
        from . import queue as q
        stats = q.stats()
        return stats.get("backend", "unknown")
    except Exception as e:
        log.warning("health: queue check failed: %s", e)
        return "down"


def _check_sentry() -> str:
    try:
        if monitoring.sentry_enabled():
            return "active"
        return "disabled"
    except Exception:
        return "down"


def _maintenance_on(db: Session) -> bool:
    """Read the maintenance flag with a defensive try/except.

    On any DB/cache error this returns False, so the worst case is
    "we ship a status payload while in maintenance" — never
    "we keep the API open when we should be closed".
    """
    try:
        return bool(utils.is_flag_enabled(db, "maintenance_mode"))
    except Exception as e:  # pragma: no cover
        log.warning("flag read failed: %s", e)
        return False


@router.get(
    "/system/status",
    response_model=SystemStatus,
    summary="Public system status (db / cache / queue / sentry / version)",
)
def system_status(
    db: Annotated[Session, Depends(get_db)],
) -> SystemStatus:
    db_state = _check_database(db)
    cache_state = _check_redis()
    queue_state = _check_queue()
    sentry_state = _check_sentry()
    # The "overall" status is "healthy" if db+cache are ok; degraded
    # if only one is down; unhealthy if db is down. This mirrors
    # what recruiters look for in a /status page.
    if db_state != "ok":
        overall = "unhealthy"
    elif cache_state == "down" and queue_state == "down":
        overall = "degraded"
    else:
        overall = "healthy"
    # Pull the canonical app version from main.py so the two places
    # can't drift apart. (Previously this endpoint returned the
    # hardcoded marketing string "1.4.0" while the OpenAPI doc and
    # the /version helper both reported the real "0.1.0" — confusing
    # for anyone who tried to cross-check.)
    try:
        from main import app as _fastapi_app
        build_version = _fastapi_app.version
    except Exception:  # pragma: no cover — e.g. test that imports in isolation
        build_version = _BUILD_VERSION
    return SystemStatus(
        status=overall,
        database=db_state,
        redis=cache_state,
        queue=queue_state,
        sentry=sentry_state,
        version=build_version,
        uptime_seconds=_time.time() - _BOOT_TIME,
        maintenance_mode=_maintenance_on(db),
        build_sha=_BUILD_SHA,
    )


@router.get(
    "/system/metrics",
    summary="Prometheus text format (text/plain; version=0.0.4)",
    response_class=__import__("fastapi.responses", fromlist=["PlainTextResponse"]).PlainTextResponse,
)
def prometheus_metrics(
    db: Annotated[Session, Depends(get_db)],
) -> "PlainTextResponse":  # type: ignore[name-defined]
    """Lightweight Prometheus text exposition. Not a full
    `prometheus_client` integration (no histograms/quantiles) — just
    the gauges and counters the monitoring dashboard reads.
    """
    from fastapi.responses import PlainTextResponse
    from . import cache, queue as q
    from .db_models import User, ChatHistory, Subscription, Payment

    lines: list[str] = []

    # ---- legacy gauges (kept for back-compat with audit6/audit7
    # tests and any external scraper that learned these names) ----
    lines.append("# HELP roastgpt_up 1 if the process is serving requests")
    lines.append("# TYPE roastgpt_up gauge")
    lines.append("roastgpt_up 1")

    # Distinct IPs currently tracked by the in-process rate limiter
    # (best-effort: we read the global from `main` if it's there).
    try:
        import main as _main_mod
        tracked = len(getattr(_main_mod, "_request_history", {}) or {})
    except Exception:
        tracked = 0
    lines.append("# HELP roastgpt_rate_limit_tracked_ips Distinct IPs currently tracked")
    lines.append("# TYPE roastgpt_rate_limit_tracked_ips gauge")
    lines.append(f"roastgpt_rate_limit_tracked_ips {tracked}")

    # ---- process info ----
    lines.append("# HELP roastgpt_build_info Static build information")
    lines.append("# TYPE roastgpt_build_info gauge")
    lines.append(
        f'roastgpt_build_info{{version="{_BUILD_VERSION}",sha="{_BUILD_SHA or "unknown"}"}} 1'
    )

    lines.append("# HELP roastgpt_uptime_seconds Seconds since the process started")
    lines.append("# TYPE roastgpt_uptime_seconds gauge")
    lines.append(f"roastgpt_uptime_seconds {round(_time.time() - _BOOT_TIME, 3)}")

    # ---- database gauges ----
    try:
        # The User model has a `deleted_at` column, but in some test
        # schemas the column may not exist (older fixtures). Fall
        # back to a plain count if the filter blows up.
        try:
            total_users = (
                db.query(func.count(User.id))
                .filter(User.deleted_at.is_(None))
                .scalar()
            )
        except Exception:
            total_users = db.query(func.count(User.id)).scalar() or 0
        total_users = total_users or 0
        active_subs = (
            db.query(func.count(Subscription.id))
            .filter(Subscription.status.in_(("active", "past_due")))
            .scalar()
            or 0
        )
        total_msgs = db.query(func.count(ChatHistory.id)).scalar() or 0
        total_payments = db.query(func.count(Payment.id)).scalar() or 0
    except Exception as e:
        log.warning("metrics: db read failed: %s", e)
        total_users = active_subs = total_msgs = total_payments = 0

    lines.append("# HELP roastgpt_users_total Total non-deleted users")
    lines.append("# TYPE roastgpt_users_total gauge")
    lines.append(f"roastgpt_users_total {total_users}")

    lines.append("# HELP roastgpt_active_subscriptions Total active or past-due subscriptions")
    lines.append("# TYPE roastgpt_active_subscriptions gauge")
    lines.append(f"roastgpt_active_subscriptions {active_subs}")

    lines.append("# HELP roastgpt_chat_messages_total Total chat history rows")
    lines.append("# TYPE roastgpt_chat_messages_total gauge")
    lines.append(f"roastgpt_chat_messages_total {total_msgs}")

    lines.append("# HELP roastgpt_payments_total Total payment rows")
    lines.append("# TYPE roastgpt_payments_total gauge")
    lines.append(f"roastgpt_payments_total {total_payments}")

    # ---- cache / queue ----
    lines.append("# HELP roastgpt_cache_backend 1=redis, 0=memory fallback")
    lines.append("# TYPE roastgpt_cache_backend gauge")
    lines.append(f"roastgpt_cache_backend {1 if cache.is_redis() else 0}")

    qstats = q.stats()
    qstate = qstats.get("backend", "unknown")
    lines.append("# HELP roastgpt_queue_backend_active 1=celery, 0=memory, -1=down")
    lines.append("# TYPE roastgpt_queue_backend_active gauge")
    if qstate == "celery":
        lines.append("roastgpt_queue_backend_active 1")
    elif qstate == "memory":
        lines.append("roastgpt_queue_backend_active 0")
    else:
        lines.append("roastgpt_queue_backend_active -1")

    # ---- health probes (0/1) ----
    db_state = _check_database(db)
    cache_state = _check_redis()
    queue_state = _check_queue()
    sentry_state = _check_sentry()
    lines.append("# HELP roastgpt_database_up 1=db reachable, 0=db down")
    lines.append("# TYPE roastgpt_database_up gauge")
    lines.append(f"roastgpt_database_up {1 if db_state == 'ok' else 0}")
    lines.append("# HELP roastgpt_cache_up 1=cache ok or in-process fallback, 0=down")
    lines.append("# TYPE roastgpt_cache_up gauge")
    lines.append(f"roastgpt_cache_up {1 if cache_state != 'down' else 0}")
    lines.append("# HELP roastgpt_queue_up 1=queue ok or in-process fallback, 0=down")
    lines.append("# TYPE roastgpt_queue_up gauge")
    lines.append(f"roastgpt_queue_up {1 if queue_state != 'down' else 0}")
    lines.append("# HELP roastgpt_sentry_up 1=sentry active, 0=disabled/down")
    lines.append("# TYPE roastgpt_sentry_up gauge")
    lines.append(f"roastgpt_sentry_up {1 if sentry_state == 'active' else 0}")

    # ---- feature flags ----
    lines.append("# HELP roastgpt_maintenance_mode 1=maintenance on, 0=off")
    lines.append("# TYPE roastgpt_maintenance_mode gauge")
    try:
        flag_val = 1 if utils.is_flag_enabled(db, "maintenance_mode") else 0
    except Exception:
        flag_val = 0
    lines.append(f"roastgpt_maintenance_mode {flag_val}")

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")
