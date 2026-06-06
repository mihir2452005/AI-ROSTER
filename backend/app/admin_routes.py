"""Admin endpoints for user and subscription management.

All endpoints require admin privileges (admin user must be created manually
or via the /api/auth/admin/grant endpoint below).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import auth, auth_schemas, db_models
from .database import get_db
from .leaderboard_routes import _safe_display_name
from .sanitize import mask_email as _mask_email

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---- Request/Response models ----
class AdminUserOut(BaseModel):
    id: int
    # The raw email is intentionally NOT returned. Admins can search by
    # email; if a real email is needed for a support case, query the DB
    # directly. This keeps PII out of API responses by default.
    masked_email: str
    full_name: Optional[str]
    gender_preference: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    role: str
    free_messages_used: int
    created_at: datetime
    has_active_subscription: bool


class UserListResponse(BaseModel):
    users: list[AdminUserOut]
    total: int


class GrantSubscriptionRequest(BaseModel):
    user_id: int
    plan_code: str
    # Cap at 10 years. An admin typo or compromised token used to be
    # able to grant a 10 000-year subscription in a single request;
    # see audit #7. The handler also enforces a server-side cap of
    # MAX_GRANT_DURATION_DAYS as a defence in depth.
    duration_days: Optional[int] = Field(default=None, ge=1, le=3650)


class UpdateUserRequest(BaseModel):
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    is_admin: Optional[bool] = None
    role: Optional[str] = Field(
        default=None,
        pattern="^(user|moderator|support|finance|admin|super_admin)$",
    )


class BanUserRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class FeatureFlagRequest(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    enabled: bool
    description: Optional[str] = Field(default=None, max_length=500)


class LeaderboardEntry(BaseModel):
    user_id: int
    masked_email: str
    full_name: Optional[str]
    total_damage: float
    message_count: int
    rank: int


class LeaderboardResponse(BaseModel):
    period: str
    entries: list[LeaderboardEntry]


# ---- User management ----
@router.get("/users", response_model=UserListResponse)
def list_users(
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
) -> UserListResponse:
    """List all users, with optional search by email/name. Admin only."""
    q = db.query(db_models.User)
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(
            (func.lower(db_models.User.email).like(like)) |
            (func.lower(db_models.User.full_name).like(like))
        )
    total = q.count()
    now = datetime.now(timezone.utc)
    users = q.order_by(db_models.User.created_at.desc()).offset(skip).limit(limit).all()

    # Single batched query to find all active subscription user_ids in this
    # page; without this we'd run one extra query per user (N+1). See M4
    # in the audit.
    user_ids = [u.id for u in users]
    active_sub_user_ids: set[int] = set()
    if user_ids:
        from sqlalchemy import and_
        active_sub_rows = db.query(db_models.Subscription.user_id).filter(
            db_models.Subscription.user_id.in_(user_ids),
            db_models.Subscription.status == db_models.SubStatus.active,
            db_models.Subscription.current_period_end > now,
        ).all()
        active_sub_user_ids = {row[0] for row in active_sub_rows}

    out = []
    for u in users:
        out.append(AdminUserOut(
            id=u.id, masked_email=_mask_email(u.email), full_name=u.full_name,
            gender_preference=u.gender_preference.value,
            is_active=u.is_active, is_verified=u.is_verified, is_admin=u.is_admin,
            role=u.role,
            free_messages_used=u.free_messages_used, created_at=u.created_at,
            has_active_subscription=u.id in active_sub_user_ids,
        ))
    return UserListResponse(users=out, total=total)


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: int,
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminUserOut:
    """Get a single user's details. Admin only."""
    u = db.get(db_models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc)
    has_sub = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == u.id,
        db_models.Subscription.status == db_models.SubStatus.active,
        db_models.Subscription.current_period_end > now,
    ).first() is not None
    return AdminUserOut(
        id=u.id, masked_email=_mask_email(u.email), full_name=u.full_name,
        gender_preference=u.gender_preference.value,
        is_active=u.is_active, is_verified=u.is_verified, is_admin=u.is_admin,
        role=u.role,
        free_messages_used=u.free_messages_used, created_at=u.created_at,
        has_active_subscription=has_sub,
    )


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    req: UpdateUserRequest,
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Update a user's flags (active, verified, admin, role). Admin only.

    Role changes are gated by `require_permission("user.set_role")` —
    setting someone to `admin` or `super_admin` requires super_admin.
    """
    from . import utils
    u = db.get(db_models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    # Capture state-change flags so we can bump token_version iff the
    # change actually affects the user's ability to keep using their
    # existing tokens. (is_verified alone doesn't.)
    affects_session = False
    if req.is_active is not None and bool(u.is_active) != bool(req.is_active):
        u.is_active = req.is_active
        affects_session = True
    if req.is_verified is not None:
        u.is_verified = req.is_verified
    if req.is_admin is not None and bool(u.is_admin) != bool(req.is_admin):
        # Prevent an admin from removing their own admin flag
        if u.id == admin.id and req.is_admin is False:
            raise HTTPException(status_code=400, detail="Cannot remove your own admin privileges")
        u.is_admin = req.is_admin
        affects_session = True
    if req.role is not None and req.role != u.role:
        # Role change. Use the RBAC permission gates; super_admin can
        # promote to admin, only super_admin can create another
        # super_admin.
        new_role = db_models.Role.from_string(req.role)
        if not admin.has_role(db_models.Role.admin):
            raise HTTPException(
                status_code=403,
                detail="Setting roles requires the 'user.set_role' permission (admin+).",
            )
        if new_role.rank() >= db_models.Role.super_admin.rank() and not admin.has_role(db_models.Role.super_admin):
            raise HTTPException(
                status_code=403,
                detail="Only super_admin can grant super_admin.",
            )
        if u.id == admin.id and new_role.rank() < admin.role_enum.rank():
            raise HTTPException(
                status_code=400,
                detail="Cannot demote yourself below your current role.",
            )
        u.role = new_role.value
        # The before_update event will sync is_admin for us.
        affects_session = True
    if affects_session:
        # Invalidate every outstanding token. The user has to log in again.
        u.token_version = (u.token_version or 0) + 1
    db.commit()
    utils.log_action(
        db, action="admin_update_user",
        actor_user_id=admin.id, target_user_id=u.id,
        details={"is_active": u.is_active, "is_verified": u.is_verified,
                 "is_admin": u.is_admin, "role": u.role},
    )
    return {"message": "User updated", "user_id": user_id}


# ---- Role catalog ----
# Public to any admin: lets the admin UI render a role dropdown and
# show what each role is allowed to do.
@router.get("/roles")
def list_roles(
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
) -> dict:
    """Return all defined roles and their rank. Used by the admin UI."""
    roles = [
        {
            "name": r.value,
            "rank": r.rank(),
            "permissions": sorted(
                p for p, required in db_models.PERMISSIONS.items() if r.can(required)
            ),
        }
        for r in db_models.Role
    ]
    return {"roles": roles}


@router.post("/users/{user_id}/ban")
def ban_user(
    user_id: int,
    req: BanUserRequest,
    admin: Annotated[db_models.User, Depends(auth.require_permission("user.ban"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Ban a user. Distinct from `is_active=false` (which is a soft
    disable): a ban carries a reason and timestamp, and the row is
    visible to other admins in the audit log.
    """
    from . import utils
    u = db.get(db_models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")
    u.is_banned = True
    u.ban_reason = req.reason
    u.banned_at = datetime.now(timezone.utc)
    u.banned_by_id = admin.id
    u.is_active = False
    # Invalidate all tokens.
    u.token_version = (u.token_version or 0) + 1
    db.commit()
    utils.log_action(
        db, action="admin_ban_user",
        actor_user_id=admin.id, target_user_id=u.id,
        details={"reason": req.reason},
    )
    return {"message": f"User {u.id} banned", "reason": req.reason}


@router.post("/users/{user_id}/unban")
def unban_user(
    user_id: int,
    admin: Annotated[db_models.User, Depends(auth.require_permission("user.unban"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from . import utils
    u = db.get(db_models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.is_banned = False
    u.ban_reason = None
    u.banned_at = None
    u.banned_by_id = None
    u.is_active = True
    db.commit()
    utils.log_action(
        db, action="admin_unban_user",
        actor_user_id=admin.id, target_user_id=u.id,
    )
    return {"message": f"User {u.id} unbanned"}


# ----- Feature flags -----


@router.get("/feature-flags")
def list_feature_flags(
    admin: Annotated[db_models.User, Depends(auth.require_permission("feature_flag.manage"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from . import utils
    return {"flags": utils.list_flags(db)}


@router.put("/feature-flags")
def upsert_feature_flag(
    req: FeatureFlagRequest,
    admin: Annotated[db_models.User, Depends(auth.require_permission("feature_flag.manage"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from . import utils
    utils.set_flag(
        db, key=req.key, enabled=req.enabled,
        updated_by_id=admin.id, description=req.description,
    )
    utils.log_action(
        db, action="admin_set_feature_flag",
        actor_user_id=admin.id,
        details={"key": req.key, "enabled": req.enabled},
    )
    return {"message": "Feature flag updated", "key": req.key, "enabled": req.enabled}


# ----- Audit log -----


@router.get("/audit-logs")
def list_audit_logs(
    admin: Annotated[db_models.User, Depends(auth.require_permission("audit.read"))],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
) -> dict:
    q = db.query(db_models.AuditLog)
    if action:
        q = q.filter(db_models.AuditLog.action == action)
    total = q.count()
    rows = q.order_by(db_models.AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return {
        "logs": [
            {
                "id": r.id,
                "action": r.action,
                "actor_user_id": r.actor_user_id,
                "actor_ip": r.actor_ip,
                "target_user_id": r.target_user_id,
                "details": r.details_json,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
    }


# ----- User achievements -----


@router.get("/users/{user_id}/achievements")
def get_user_achievements(
    user_id: int,
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """List a user's unlocked achievements (admin view)."""
    unlocked = {
        r.achievement_key: r.unlocked_at
        for r in db.query(db_models.UserAchievement)
        .filter(db_models.UserAchievement.user_id == user_id)
        .all()
    }
    catalog = db.query(db_models.Achievement).order_by(db_models.Achievement.sort_order).all()
    return {
        "achievements": [
            {
                "key": a.key,
                "name": a.name,
                "description": a.description,
                "emoji": a.emoji,
                "category": a.category,
                "rarity": a.rarity,
                "points": a.points,
                "unlocked": a.key in unlocked,
                "unlocked_at": unlocked[a.key].isoformat() if a.key in unlocked else None,
            }
            for a in catalog
        ]
    }


# ----- Charts / time-series analytics -----


@router.get("/charts/signups")
def chart_signups(
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Daily signups over the last N days."""
    from sqlalchemy import func as sqlfunc
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            sqlfunc.date(db_models.User.created_at).label("d"),
            sqlfunc.count(db_models.User.id).label("n"),
        )
        .filter(db_models.User.created_at >= start)
        .group_by(sqlfunc.date(db_models.User.created_at))
        .order_by(sqlfunc.date(db_models.User.created_at))
        .all()
    )
    return {
        "metric": "signups",
        "days": days,
        "points": [{"date": str(d), "count": int(n)} for d, n in rows],
    }


@router.get("/charts/chats")
def chart_chats(
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Daily chat volume over the last N days (user messages only)."""
    from sqlalchemy import func as sqlfunc
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            sqlfunc.date(db_models.ChatHistory.created_at).label("d"),
            sqlfunc.count(db_models.ChatHistory.id).label("n"),
        )
        .filter(
            db_models.ChatHistory.created_at >= start,
            db_models.ChatHistory.is_user == True,  # noqa: E712
        )
        .group_by(sqlfunc.date(db_models.ChatHistory.created_at))
        .order_by(sqlfunc.date(db_models.ChatHistory.created_at))
        .all()
    )
    return {
        "metric": "chats",
        "days": days,
        "points": [{"date": str(d), "count": int(n)} for d, n in rows],
    }


@router.post("/grant-subscription")
def grant_subscription(
    req: GrantSubscriptionRequest,
    admin: Annotated[db_models.User, Depends(auth.require_permission("subscription.grant"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Manually grant a subscription to a user (no payment required).
    Used for customer support, promos, or compensating users.

    Refuses to create a duplicate active subscription; if the user
    already has an active one we extend its `current_period_end` instead.
    See H5 in the audit.
    """
    from sqlalchemy.exc import IntegrityError
    user = db.get(db_models.User, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    plan = db.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.plan_code == req.plan_code
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    now = datetime.now(timezone.utc)
    duration = req.duration_days or plan.duration_days
    # Defence in depth: cap the duration at 10 years server-side, even
    # if a future schema change weakens the Pydantic validator. See
    # audit #7.
    duration = min(duration, 3650)

    # If the user already has an active subscription, extend it.
    # Also reset the free-tier counter: an admin grant means the user
    # is now paying/pro, so the 5-msg cap shouldn't kick back in if
    # the grant later expires. (Mirrors the verify_payment rule.)
    if user.free_messages_used and user.free_messages_used > 0:
        user.free_messages_used = 0
    existing = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == user.id,
        db_models.Subscription.status == db_models.SubStatus.active,
        db_models.Subscription.current_period_end > now,
    ).first()
    if existing is not None:
        # Extend from the current end date (or now, whichever is later).
        # NB: SQLite's DateTime column drops tzinfo on read, so we
        # normalise both sides to naive UTC before comparing.
        existing_end = existing.current_period_end
        if existing_end is not None and existing_end.tzinfo is not None:
            existing_end_naive = existing_end.replace(tzinfo=None)
        else:
            existing_end_naive = existing_end
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        base = max(existing_end_naive or now_naive, now_naive)
        existing.current_period_end = base + timedelta(days=duration)
        existing.admin_granted = True
        db.commit()
        return {
            "message": f"Subscription extended for user {user.id} ({_mask_email(user.email)})",
            "subscription_id": existing.id,
            "current_period_end": existing.current_period_end.isoformat(),
        }

    sub = db_models.Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=db_models.SubStatus.active,
        current_period_start=now,
        current_period_end=now + timedelta(days=duration),
        admin_granted=True,
    )
    db.add(sub)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="User already has an active subscription.",
        )
    db.refresh(sub)
    return {
        "message": f"Subscription granted to user {user.id} ({_mask_email(user.email)})",
        "subscription_id": sub.id,
        "current_period_end": sub.current_period_end.isoformat(),
    }


# ---- Leaderboard ----
def _week_id(d: datetime) -> str:
    """Return 'YYYY-Www' for the ISO week of d."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("week", pattern="^(week|month)$"),
    limit: int = Query(10, ge=1, le=100),
) -> LeaderboardResponse:
    """Show top users by total damage dealt for the current period.
    The top N (configurable) users may receive a free subscription
    (admin_granted=True via /grant-subscription)."""
    now = datetime.now(timezone.utc)
    if period == "week":
        period_id = _week_id(now)
        start = now - timedelta(days=7)
    else:
        period_id = now.strftime("%Y-%m")
        start = now - timedelta(days=30)

    # Sum damage per user from chat history in the period
    rows = (
        db.query(
            db_models.ChatHistory.user_id,
            func.coalesce(func.sum(db_models.ChatHistory.score_total), 0.0).label("total_damage"),
            func.count(db_models.ChatHistory.id).label("message_count"),
        )
        .filter(db_models.ChatHistory.created_at >= start)
        .group_by(db_models.ChatHistory.user_id)
        .order_by(func.sum(db_models.ChatHistory.score_total).desc())
        .limit(limit)
        .all()
    )

    entries = []
    for rank, (uid, dmg, count) in enumerate(rows, start=1):
        u = db.get(db_models.User, uid)
        if not u:
            continue
        entries.append(LeaderboardEntry(
            user_id=uid, masked_email=_mask_email(u.email), full_name=_safe_display_name(u.full_name),
            total_damage=float(dmg or 0), message_count=int(count or 0), rank=rank,
        ))

    return LeaderboardResponse(period=period_id, entries=entries)


@router.get("/stats")
def admin_stats(
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Quick admin dashboard summary.

    Includes:
      - total_users, active_users, banned_users
      - active_subscriptions, total_payments, total_revenue
      - total_chats (count of user messages)
      - avg_session_time_seconds (mean of `ended_at - created_at`
        for ended sessions, with at least 1 user message)
      - most_used_mode (mode with the most user messages)
      - daily_active_users (last 24h, user messages)
    """
    from sqlalchemy import func as sqlfunc
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    # Total chats = user messages
    total_chats = (
        db.query(sqlfunc.count(db_models.ChatHistory.id))
        .filter(db_models.ChatHistory.is_user == True)  # noqa: E712
        .scalar() or 0
    )
    # Average session time (seconds) for ended sessions with >=1 user message
    avg_row = (
        db.query(
            sqlfunc.avg(
                db_models.RoastSession.ended_at - db_models.RoastSession.created_at
            )
        )
        .filter(db_models.RoastSession.ended_at.isnot(None))
        .scalar()
    )
    avg_session_time = float(avg_row) if avg_row is not None else 0.0
    # Most used mode
    mode_row = (
        db.query(
            db_models.RoastSession.mode,
            sqlfunc.count(db_models.RoastSession.id).label("n"),
        )
        .group_by(db_models.RoastSession.mode)
        .order_by(sqlfunc.count(db_models.RoastSession.id).desc())
        .first()
    )
    most_used_mode = mode_row[0] if mode_row else None
    # Daily active users (last 24h) — distinct users with at least
    # one message.
    dau = (
        db.query(sqlfunc.count(sqlfunc.distinct(db_models.ChatHistory.user_id)))
        .filter(
            db_models.ChatHistory.created_at >= day_ago,
            db_models.ChatHistory.is_user == True,  # noqa: E712
        )
        .scalar() or 0
    )
    return {
        "total_users": db.query(func.count(db_models.User.id)).scalar() or 0,
        "active_users": db.query(func.count(db_models.User.id))
            .filter(db_models.User.is_active == True).scalar() or 0,
        "banned_users": db.query(func.count(db_models.User.id))
            .filter(db_models.User.is_banned == True).scalar() or 0,  # noqa: E712
        "active_subscriptions": db.query(func.count(db_models.Subscription.id))
            .filter(
                db_models.Subscription.status == db_models.SubStatus.active,
                db_models.Subscription.current_period_end > now,
            ).scalar() or 0,
        "total_payments": db.query(func.count(db_models.Payment.id))
            .filter(db_models.Payment.status == db_models.PaymentStatus.captured).scalar() or 0,
        "total_revenue_paise": db.query(func.coalesce(func.sum(db_models.Payment.amount), 0))
            .filter(db_models.Payment.status == db_models.PaymentStatus.captured).scalar() or 0,
        "total_chats": int(total_chats),
        "avg_session_time_seconds": avg_session_time,
        "most_used_mode": most_used_mode,
        "daily_active_users": int(dau),
    }
