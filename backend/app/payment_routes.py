"""Payment integration with Razorpay.

Endpoints:
- POST /api/payments/plans             - list available plans
- POST /api/payments/create-order      - create a Razorpay order for a plan
- POST /api/payments/verify            - verify payment signature after checkout
- POST /api/payments/webhook           - Razorpay webhook receiver
- GET  /api/payments/history           - current user's payment history
- GET  /api/subscriptions/me           - current user's subscriptions
- POST /api/subscriptions/cancel       - cancel active subscription
"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Annotated

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from . import auth, auth_schemas, db_models
from .database import get_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])
sub_router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def _is_sub_live(sub: db_models.Subscription) -> bool:
    """Return True iff the subscription should grant access right now.

    A subscription is "live" if:
      - status is active or past_due
      - current_period_end is set and in the future
    `pending` and `cancelled` subs do NOT grant access. Subs with
    current_period_end=None are treated as expired (defensive: schema
    allows it; the value should always be set on a real sub).
    """
    if sub.status not in (db_models.SubStatus.active, db_models.SubStatus.past_due):
        return False
    if sub.current_period_end is None:
        return False
    # Normalise to UTC-naive so we can compare across SQLite (drops
    # tzinfo) and PostgreSQL (preserves it). The values are always
    # UTC-stored.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    end = sub.current_period_end
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return end > now


# ---- Razorpay client ----
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")


def get_razorpay_client() -> razorpay.Client:
    # Re-read the env vars on every call so an operator can rotate the
    # Razorpay keypair in their hosting dashboard without a process
    # restart. See audit #17.
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=503,
            detail="Payment gateway not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
        )
    return razorpay.Client(auth=(key_id, key_secret))


# ---- Plans (seed defaults if empty) ----
# Each plan has TWO feature keys:
#   1. A machine-readable schema (roaster_types, unlimited, etc.) used
#      by the API consumers that want to gate behaviour on plan.
#   2. A `items` list and optional `highlighted` string used by the
#      pricing page UI to render feature bullets. Keeping the list on
#      the backend means changing copy doesn't require a frontend deploy.
DEFAULT_PLANS = [
    {
        "plan_code": "starter",
        "name": "Starter Chat",
        "price_paise": 29900,  # ₹299
        "duration_days": 10,
        "features": {
            "roaster_types": ["male", "female"],
            "unlimited": True,
            "priority_support": False,
            "items": [
                "✅ Unlimited messages",
                "✅ Male & female roaster",
                "✅ Chat history",
                "❌ Custom personality",
            ],
        },
    },
    {
        "plan_code": "pro",
        "name": "Pro Roaster",
        "price_paise": 79900,  # ₹799
        "duration_days": 30,
        "features": {
            "roaster_types": ["male", "female", "neutral"],
            "unlimited": True,
            "priority_support": True,
            "highlighted": "MOST POPULAR",
            "items": [
                "✅ Everything in Starter",
                "✅ All 3 roaster types",
                "✅ Priority support",
                "✅ Weekly leaderboard rewards",
            ],
        },
    },
    {
        "plan_code": "legend",
        "name": "Legend Pass",
        "price_paise": 199900,  # ₹1999
        "duration_days": 90,
        "features": {
            "roaster_types": ["male", "female", "neutral", "custom"],
            "unlimited": True,
            "priority_support": True,
            "custom_personality": True,
            "items": [
                "✅ Everything in Pro",
                "✅ Custom personality (build your own)",
                "✅ 90 days of access",
                "✅ VIP support & early features",
            ],
        },
    },
]


def seed_plans(db: Session) -> None:
    """Insert default plans if the table is empty, and merge any new
    feature keys (e.g. `items` for the pricing page UI) into existing
    plans so the seed is forward-compatible.

    Idempotent: safe to call on every boot. Existing rows are merged
    by `plan_code`, so renaming a plan still works. Custom plans
    (e.g. added by an admin via SQL) are left alone unless their
    `plan_code` matches a default — in which case the seeded fields
    fill in only the keys that are missing.
    """
    for p in DEFAULT_PLANS:
        existing = db.query(db_models.SubscriptionPlan).filter(
            db_models.SubscriptionPlan.plan_code == p["plan_code"]
        ).first()
        if existing is None:
            db.add(db_models.SubscriptionPlan(**p))
        else:
            # Forward-compat: if the existing row is missing any of the
            # feature keys shipped in this build's DEFAULT_PLANS, add
            # them. This is what brings an older DB up to date with a
            # new `items` list without overwriting admin customisations.
            merged = dict(existing.features or {})
            changed = False
            for k, v in (p.get("features") or {}).items():
                if k not in merged:
                    merged[k] = v
                    changed = True
            if changed:
                existing.features = merged
    db.commit()


@router.get("/plans", response_model=auth_schemas.PlanList)
def list_plans(
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.PlanList:
    """List all active subscription plans."""
    seed_plans(db)
    plans = db.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.is_active == True
    ).all()
    return auth_schemas.PlanList(plans=[
        auth_schemas.PlanOut(
            id=p.id,
            plan_code=p.plan_code,
            name=p.name,
            price_paise=p.price_paise,
            price_display=f"₹{p.price_paise / 100:.2f}",
            currency=p.currency,
            duration_days=p.duration_days,
            features=p.features or {},
        )
        for p in plans
    ])


@router.post("/create-order", response_model=auth_schemas.CreateOrderResponse)
def create_order(
    req: auth_schemas.CreateOrderRequest,
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.CreateOrderResponse:
    """Create a Razorpay order for a given plan and return order details
    that the frontend uses to open the checkout widget.

    Refuses to create a new order if the user already has an active
    subscription — paying twice for the same plan is a billing bug
    waiting to happen. See H1 in the audit.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Refuse to create a new order if the user has a LIVE subscription
    # (active/pending/past_due with future period end). Expired
    # subscriptions and cancelled ones are fine — the user is allowed
    # to re-subscribe. (Prior bug: an expired sub would block
    # re-purchase until admin manually marked it completed. The
    # periodic cleanup task now marks expired subs as completed, but
    # we also defend here so the user is never permanently locked out.)
    existing = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == user.id,
        db_models.Subscription.status.in_([
            db_models.SubStatus.active,
            db_models.SubStatus.past_due,
            db_models.SubStatus.pending,
        ]),
        db_models.Subscription.current_period_end > now,
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "You already have an active or pending subscription. "
                "Cancel it before starting a new one, or contact support."
            ),
        )

    plan = db.query(db_models.SubscriptionPlan).filter(
        db_models.SubscriptionPlan.plan_code == req.plan_code,
        db_models.SubscriptionPlan.is_active == True,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    client = get_razorpay_client()
    order_data = client.order.create({
        "amount": plan.price_paise,
        "currency": plan.currency,
        "receipt": f"order_{user.id}_{int(time.time())}",
        "payment_capture": 1,
        "notes": {
            "user_id": str(user.id),
            "plan_code": plan.plan_code,
        },
    })

    # Create a pending subscription record so we can attach the payment later.
    sub = db_models.Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=db_models.SubStatus.pending,
        razorpay_order_id=order_data["id"],
    )
    db.add(sub)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent create-order by the same user beat us to it. Roll
        # back and return a clean 409. NB: the Razorpay order we just
        # created is now orphaned on Razorpay's side. We can't refund
        # it automatically (no payment was made yet), but Razorpay
        # auto-expires unpaid orders in ~24h, so this is a soft leak
        # at worst. See BUG-PAY-005.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another subscription request is in flight. Try again.",
        )
    db.refresh(sub)

    return auth_schemas.CreateOrderResponse(
        order_id=order_data["id"],
        amount=plan.price_paise,
        currency=plan.currency,
        plan_code=plan.plan_code,
        plan_name=plan.name,
        key_id=RAZORPAY_KEY_ID,
    )


@router.post("/verify")
def verify_payment(
    req: auth_schemas.VerifyPaymentRequest,
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Verify a payment after the user completes the Razorpay checkout.
    On success, mark the subscription active and grant the user access.

    Idempotent: if a Payment with the same razorpay_payment_id already
    exists, return the previously-issued subscription info instead of
    creating a duplicate.
    """
    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature({
            "order_id": req.razorpay_order_id,
            "payment_id": req.razorpay_payment_id,
            "signature": req.razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Idempotency: if this payment_id has already been processed (e.g. the
    # user re-loaded the success page), return the existing subscription
    # state rather than creating a second Subscription / Payment row.
    # The lookup is scoped to this user so we can't leak another user's
    # subscription_id via a guessed payment_id. See M1 in the audit.
    existing_payment = db.query(db_models.Payment).filter(
        db_models.Payment.razorpay_payment_id == req.razorpay_payment_id,
        db_models.Payment.user_id == user.id,
    ).first()
    if existing_payment is not None:
        existing_sub = existing_payment.subscription
        if existing_sub is None:
            # Orphaned payment from a partial earlier run. Look it up by
            # order_id so we can still return a sensible response.
            existing_sub = db.query(db_models.Subscription).filter(
                db_models.Subscription.razorpay_order_id == req.razorpay_order_id,
                db_models.Subscription.user_id == user.id,
            ).first()
        return {
            "message": "Payment already verified",
            "subscription_id": existing_sub.id if existing_sub else None,
            "current_period_end": (
                existing_sub.current_period_end.isoformat()
                if existing_sub and existing_sub.current_period_end else None
            ),
        }

    # Find the subscription by order_id
    sub = db.query(db_models.Subscription).filter(
        db_models.Subscription.razorpay_order_id == req.razorpay_order_id,
        db_models.Subscription.user_id == user.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    plan = sub.plan
    now = datetime.now(timezone.utc)

    # Activate the subscription, but don't reset the billing period if
    # it's already active. Re-activating on every verify call would
    # extend a user's access on every page reload, which is a billing
    # bug. We also refuse to re-activate a subscription the user (or
    # admin) has explicitly cancelled — see BUG-PAY-012 below; the
    # webhook handler shares the same rule.
    if sub.status == db_models.SubStatus.active and sub.current_period_end and sub.current_period_end > now:
        # Already active and not expired. Leave period as-is.
        pass
    elif sub.status == db_models.SubStatus.cancelled and sub.cancel_at_period_end:
        # User cancelled. Don't silently re-activate. The admin can
        # grant a new sub via /api/admin/grant-subscription if needed.
        raise HTTPException(
            status_code=409,
            detail="Subscription was cancelled. Contact support to reactivate.",
        )
    else:
        sub.status = db_models.SubStatus.active
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=plan.duration_days)
        # Reset the cancellation flag if the sub was previously
        # scheduled to cancel at period end (a fresh payment means the
        # user changed their mind). This is the only case where we DO
        # override the cancelled state.
        sub.cancel_at_period_end = False
        # Reset the free-tier counter: a paying user shouldn't be
        # locked out of the free tier later when their subscription
        # expires. (Prior bug: a user with free_messages_used=5 who
        # then subscribed was permanently locked out of the free tier
        # after the sub expired. See BUG-PAY-035.)
        if user.free_messages_used and user.free_messages_used > 0:
            user.free_messages_used = 0
    # NOTE: do NOT write req.razorpay_payment_id into sub.razorpay_subscription_id.
    # That column is reserved for Razorpay subscription IDs (used by the
    # `subscription.cancelled` webhook lookup) — see H4 in the audit.

    payment = db_models.Payment(
        user_id=user.id,
        subscription_id=sub.id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_order_id=req.razorpay_order_id,
        razorpay_signature=req.razorpay_signature,
        amount=plan.price_paise,
        currency=plan.currency,
        status=db_models.PaymentStatus.captured,
        description=f"Subscription to {plan.name}",
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        # Another request beat us to it; fall back to read-only response.
        db.rollback()
        existing_payment = db.query(db_models.Payment).filter(
            db_models.Payment.razorpay_payment_id == req.razorpay_payment_id,
        ).first()
        existing_sub = existing_payment.subscription if existing_payment else None
        return {
            "message": "Payment already verified",
            "subscription_id": existing_sub.id if existing_sub else None,
            "current_period_end": (
                existing_sub.current_period_end.isoformat()
                if existing_sub and existing_sub.current_period_end else None
            ),
        }
    db.refresh(sub)

    return {
        "message": "Payment verified and subscription activated",
        "subscription_id": sub.id,
        "current_period_end": sub.current_period_end.isoformat(),
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Receive Razorpay webhook events. Verifies signature and updates state
    for events like subscription.cancelled, payment.failed, etc."""
    if not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    client = get_razorpay_client()
    try:
        client.utility.verify_webhook_signature(
            body.decode(), signature, RAZORPAY_WEBHOOK_SECRET
        )
    except Exception:
        # Don't log the exception object — an attacker flooding us with
        # bad signatures would otherwise fill the log. Just a brief
        # counter-style warning. See H7 in the audit.
        log.warning("Razorpay webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    import json
    event = json.loads(body)
    event_type = event.get("event")
    log.info("Razorpay webhook: %s", event_type)

    if event_type == "payment.captured":
        payload = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payload.get("order_id")
        payment_id = payload.get("id")
        if order_id:
            sub = db.query(db_models.Subscription).filter(
                db_models.Subscription.razorpay_order_id == order_id
            ).first()
            # Defence in depth: cross-check the user_id from the order
            # notes against the subscription's user_id. If they disagree,
            # a previous bug or a manual DB edit has caused a mismatch —
            # log and ignore. See audit #6.
            note_user_id = (event.get("payload", {}).get("order", {})
                            .get("entity", {}).get("notes", {}).get("user_id"))
            if sub and note_user_id and str(sub.user_id) != str(note_user_id):
                log.error(
                    "Razorpay webhook: user_id mismatch on payment.captured: "
                    "order=%s notes.user_id=%s sub.user_id=%s",
                    order_id, note_user_id, sub.user_id,
                )
                sub = None
            # Idempotency: only act if the subscription is NOT already
            # active with a future period end. Re-activating on every
            # webhook delivery would re-extend the billing window.
            # Mirrors the verify_payment rules.
            now = datetime.now(timezone.utc)
            if sub and not (
                sub.status == db_models.SubStatus.active
                and sub.current_period_end
                and sub.current_period_end > now
            ) and sub.status != db_models.SubStatus.cancelled:
                plan = sub.plan
                sub.status = db_models.SubStatus.active
                sub.current_period_start = now
                sub.current_period_end = now + timedelta(days=plan.duration_days)
                sub.cancel_at_period_end = False
                # Reset free-tier counter on fresh activation.
                user = sub.user
                if user and user.free_messages_used and user.free_messages_used > 0:
                    user.free_messages_used = 0
            # Record the payment if the verify endpoint hasn't already.
            # Idempotent: payment_id has a unique constraint, so a duplicate
            # webhook just becomes a no-op.
            if payment_id and sub is not None and not db.query(
                db_models.Payment
            ).filter(db_models.Payment.razorpay_payment_id == payment_id).first():
                db.add(db_models.Payment(
                    user_id=sub.user_id,
                    subscription_id=sub.id,
                    razorpay_payment_id=payment_id,
                    razorpay_order_id=order_id,
                    amount=payload.get("amount", sub.plan.price_paise),
                    currency=payload.get("currency", sub.plan.currency),
                    status=db_models.PaymentStatus.captured,
                    payment_method=(payload.get("method") or None),
                    description=f"Subscription to {sub.plan.name} (webhook)",
                ))
            try:
                db.commit()
            except IntegrityError:
                # Another webhook or the verify endpoint beat us to it.
                # Not an error; webhooks are at-least-once.
                db.rollback()

    elif event_type == "subscription.cancelled":
        payload = event.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = payload.get("id")
        if sub_id:
            sub = db.query(db_models.Subscription).filter(
                db_models.Subscription.razorpay_subscription_id == sub_id
            ).first()
            # Mark cancelled AND set cancel_at_period_end so the user
            # keeps access until the period end. Mirrors the
            # /api/subscriptions/cancel flow. (Prior bug: status was
            # set to cancelled but cancel_at_period_end stayed False,
            # making the UI show the user as "active" while the system
            # treated them as cancelled.)
            if sub and sub.status != db_models.SubStatus.cancelled:
                sub.status = db_models.SubStatus.cancelled
                sub.cancel_at_period_end = True
                db.commit()

    elif event_type == "payment.failed":
        payload = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payload.get("order_id")
        if order_id:
            sub = db.query(db_models.Subscription).filter(
                db_models.Subscription.razorpay_order_id == order_id
            ).first()
            # A failed payment should leave the user in `past_due` so
            # they can retry — NOT `cancelled`, which would lock them
            # out of re-subscribing until the admin intervened.
            # (Prior bug: failed payment marked sub as cancelled.)
            if sub and sub.status == db_models.SubStatus.pending:
                sub.status = db_models.SubStatus.past_due
                db.commit()

    elif event_type == "refund.processed":
        # A refund was issued. Mark the payment as refunded and cancel
        # the subscription. The access-grace is governed by
        # `cancel_at_period_end`; since the user got their money back
        # there's no grace — they lose access immediately.
        payload = event.get("payload", {}).get("refund", {}).get("entity", {})
        payment_id = payload.get("payment_id")
        if payment_id:
            payment = db.query(db_models.Payment).filter(
                db_models.Payment.razorpay_payment_id == payment_id
            ).first()
            if payment:
                payment.status = db_models.PaymentStatus.refunded
                sub = payment.subscription
                if sub and sub.status != db_models.SubStatus.cancelled:
                    sub.status = db_models.SubStatus.cancelled
                    sub.cancel_at_period_end = False
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()

    elif event_type == "subscription.halted":
        # Razorpay halted the subscription (auto-debit failure). Move
        # to past_due so the user can re-subscribe.
        payload = event.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = payload.get("id")
        if sub_id:
            sub = db.query(db_models.Subscription).filter(
                db_models.Subscription.razorpay_subscription_id == sub_id
            ).first()
            if sub and sub.status == db_models.SubStatus.active:
                sub.status = db_models.SubStatus.past_due
                db.commit()

    elif event_type == "subscription.completed":
        payload = event.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = payload.get("id")
        if sub_id:
            sub = db.query(db_models.Subscription).filter(
                db_models.Subscription.razorpay_subscription_id == sub_id
            ).first()
            if sub and sub.status not in (
                db_models.SubStatus.cancelled,
                db_models.SubStatus.completed,
            ):
                sub.status = db_models.SubStatus.completed
                db.commit()

    return {"received": True}


@router.get("/history", response_model=list[auth_schemas.PaymentOut])
def payment_history(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[auth_schemas.PaymentOut]:
    """Return the current user's payment history, newest first."""
    payments = db.query(db_models.Payment).filter(
        db_models.Payment.user_id == user.id
    ).order_by(db_models.Payment.created_at.desc()).limit(50).all()
    return [
        auth_schemas.PaymentOut(
            id=p.id,
            amount=p.amount,
            currency=p.currency,
            status=p.status.value,
            description=p.description,
            created_at=p.created_at,
        )
        for p in payments
    ]


# ---- Subscriptions ----
@sub_router.get("/me", response_model=auth_schemas.SubscriptionList)
def my_subscriptions(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.SubscriptionList:
    """List the current user's subscriptions, newest first."""
    subs = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == user.id
    ).order_by(db_models.Subscription.created_at.desc()).all()
    return auth_schemas.SubscriptionList(subscriptions=[
        auth_schemas.SubscriptionOut(
            id=s.id,
            plan_code=s.plan.plan_code,
            plan_name=s.plan.name,
            status=s.status.value,
            current_period_start=s.current_period_start,
            current_period_end=s.current_period_end,
            cancel_at_period_end=s.cancel_at_period_end,
            admin_granted=s.admin_granted,
            created_at=s.created_at,
        )
        for s in subs
    ])


@sub_router.post("/cancel")
def cancel_subscription(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Cancel the current user's active subscription (sets cancel_at_period_end=True).
    Access continues until the end of the current period."""
    sub = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == user.id,
        db_models.Subscription.status == db_models.SubStatus.active,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription")
    sub.cancel_at_period_end = True
    db.commit()
    return {
        "message": "Subscription will be cancelled at the end of the current period",
        "current_period_end": sub.current_period_end.isoformat(),
    }
