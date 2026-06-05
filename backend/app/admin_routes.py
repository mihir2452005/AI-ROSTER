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
    """Update a user's flags (active, verified, admin). Admin only."""
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
    if affects_session:
        # Invalidate every outstanding token. The user has to log in again.
        u.token_version = (u.token_version or 0) + 1
    db.commit()
    return {"message": "User updated", "user_id": user_id}


@router.post("/grant-subscription")
def grant_subscription(
    req: GrantSubscriptionRequest,
    admin: Annotated[db_models.User, Depends(auth.require_admin)],
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
    """Quick admin dashboard summary."""
    now = datetime.now(timezone.utc)
    return {
        "total_users": db.query(func.count(db_models.User.id)).scalar() or 0,
        "active_users": db.query(func.count(db_models.User.id))
            .filter(db_models.User.is_active == True).scalar() or 0,
        "active_subscriptions": db.query(func.count(db_models.Subscription.id))
            .filter(
                db_models.Subscription.status == db_models.SubStatus.active,
                db_models.Subscription.current_period_end > now,
            ).scalar() or 0,
        "total_payments": db.query(func.count(db_models.Payment.id))
            .filter(db_models.Payment.status == db_models.PaymentStatus.captured).scalar() or 0,
        "total_revenue_paise": db.query(func.coalesce(func.sum(db_models.Payment.amount), 0))
            .filter(db_models.Payment.status == db_models.PaymentStatus.captured).scalar() or 0,
    }
