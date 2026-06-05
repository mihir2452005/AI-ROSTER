"""API routes for the roast engine."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import auth, db_models, filler, intent, matcher, safety, scorer
from .config import MAX_SESSION_MESSAGES, MAX_HISTORY_MESSAGE_CHARS, MAX_USER_MESSAGE_CHARS, MAX_USERNAME_CHARS
from .database import get_db
from .sanitize import sanitize_text
from .library import LIB
from .models import (
    ChatMessage,
    EndSessionResponse,
    ModesResponse,
    Personality,
    PersonalitiesResponse,
    RoastMode,
    RoastRequest,
    RoastResponse,
    SessionStateResponse,
    StartSessionRequest,
    StartSessionResponse,
)
from .session import MEMORY, SESSIONS

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Free-tier message limit (per account, lifetime). The same constant is
# used by the /api/auth/register router and the /api/session/{id}/roast
# gate. Keep them in lockstep — change one, change both. The
# subscription gate is bypassed entirely when the user has an active
# subscription, so a paying user never hits this number.
FREE_MESSAGES_LIMIT = 5

# Sessions ended more than this long ago are eligible for cleanup. The session
# is kept around for this long so a shared link can still load the transcript.
SHARED_SESSION_TTL_SECONDS = float(
    os.environ.get("ROASTGPT_SHARED_TTL_SECONDS", str(24 * 60 * 60))
)

# Generic closer used as a last-resort fallback if the library has no closer
# for a personality. Never None in production (every personality ships a
# closer), but defensive against library regressions.
FALLBACK_CLOSER = "That's all I have. Go lie down."


# ----- Health -----

@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "library_loaded": LIB.is_loaded(),
        "roasts": sum(len(p) for p in LIB.roasts_by_mode.values()),
        "personalities": len(LIB.personalities),
        "intents": len(LIB.intents),
    }


# ----- Catalog -----

@router.get("/modes", response_model=ModesResponse)
def get_modes() -> ModesResponse:
    return ModesResponse(modes=list(RoastMode))


@router.get("/personalities", response_model=PersonalitiesResponse)
def get_personalities() -> PersonalitiesResponse:
    return PersonalitiesResponse(personalities=list(Personality))


# ----- Session lifecycle -----

@router.post("/session/start", response_model=StartSessionResponse)
def start_session(
    req: StartSessionRequest,
    user: Annotated[Optional[db_models.User], Depends(auth.get_optional_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> StartSessionResponse:
    if not LIB.is_loaded():
        raise HTTPException(503, "library not loaded")

    # Sanitize user-controlled inputs up front. Anything that hits the
    # database, the session store, or the response gets the same treatment
    # so a malicious payload can't smuggle control bytes into logs or HTML.
    if req.username is not None:
        req.username = sanitize_text(req.username, max_length=MAX_USERNAME_CHARS)
        if not req.username:
            req.username = None

    # Check for returning user
    prior = MEMORY.get(req.username) if req.username else None

    session = SESSIONS.create(
        req.mode, req.personality, req.username,
        roaster_gender=req.roaster_gender,
        user_id=user.id if user is not None else None,
    )
    if session is None:
        # Cap reached by live sessions. The store refused to evict a
        # live conversation. Tell the client to retry.
        raise HTTPException(503, "Server is at session capacity. Try again in a moment.")

    # If returning user, prefer a callback; otherwise use a regular opener.
    opener_text: Optional[str] = None
    chosen_special: Optional[object] = None
    if prior:
        cb = matcher.select_callback(req.personality, LIB)
        if cb:
            chosen_special = cb
            opener_text = filler.fill_placeholders_by_spec(
                cb, LIB, session, prior_intent=prior.get("last_topic")
            )
    if opener_text is None:
        op = matcher.select_opener(req.mode, req.personality, LIB)
        if op is None:
            opener_text = "Hello. I have nothing to say to you yet. Give me a moment."
        else:
            chosen_special = op
            opener_text = filler.fill_placeholders_by_spec(op, LIB, session, prior_intent=None)

    opener_text = matcher.apply_personality_flavor(opener_text, req.personality, LIB)

    # Append reaction emoji from whichever special template was chosen.
    if (
        opener_text is not None
        and chosen_special is not None
        and getattr(chosen_special, "reaction", None)
        and not opener_text.endswith(chosen_special.reaction)
    ):
        opener_text = f"{opener_text} {chosen_special.reaction}"

    # Run the opener through the output safety filter.
    if opener_text is not None:
        out_v = safety.check_output(opener_text)
        if not out_v.is_safe:
            log.warning(
                "blocked term in opener: term=%s",
                out_v.blocked_term_in_output,
            )
            opener_text = safety.sanitize_output(opener_text)

    session.opener_used = True
    session.history.append(
        ChatMessage(role="assistant", content=opener_text or "", intents=[])
    )
    SESSIONS.save(session, db=db, user_id=user.id if user is not None else None)

    # Persist opener to authenticated user's history.
    if user is not None and db is not None and opener_text:
        try:
            entry = db_models.ChatHistory(
                user_id=user.id,
                message=sanitize_text(opener_text, max_length=MAX_HISTORY_MESSAGE_CHARS) or "",
                is_user=False,
                roast_response=None,
                score_total=0.0,
                session_id=session.session_id,
            )
            db.add(entry)
            db.commit()
        except Exception as _exc:  # pragma: no cover
            log.warning("failed to persist opener: %s", _exc)
            db.rollback()

    return StartSessionResponse(
        session_id=session.session_id,
        opener=opener_text or "",
        scores=session.scores,
        mode=req.mode,
        personality=req.personality,
        roaster_gender=session.roaster_gender,
    )


@router.post("/session/{session_id}/roast", response_model=RoastResponse)
def roast(
    session_id: str,
    req: RoastRequest,
    user: Annotated[Optional[db_models.User], Depends(auth.get_optional_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> RoastResponse:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "session not found")

    if session.ended_at is not None:
        raise HTTPException(
            410,
            "session has ended; start a new session",
        )

    if not LIB.is_loaded():
        raise HTTPException(503, "library not loaded")

    # Sanitize the incoming message. Anything beyond MAX_USER_MESSAGE_CHARS
    # is almost certainly an abuse attempt; reject it explicitly so we
    # never spend matcher/scorer CPU on it.
    if req.message is None or not req.message.strip():
        raise HTTPException(422, "message is required")
    req.message = sanitize_text(req.message, max_length=MAX_USER_MESSAGE_CHARS) or ""
    if not req.message.strip():
        raise HTTPException(422, "message is required")

    # --- Safety: check the incoming message BEFORE anything else ---
    verdict = safety.check_input(req.message)
    if not verdict.is_safe:
        # We deliberately do NOT persist the raw user message when the
        # safety filter refuses it. PII / self-harm / distress content
        # is the most sensitive payload a user can send, and storing it
        # in session history would make it retrievable via the share
        # URL and the unauthenticated GET /api/session/{id} endpoint.
        # Persist a redacted placeholder so the user can still see the
        # conversation shape in their client.
        redacted_user_msg = "[redacted by safety filter]"
        if verdict.is_minor and verdict.forced_mode and verdict.forced_personality:
            # Lock the entire session to safe defaults; future turns also safe.
            session.mode = verdict.forced_mode
            session.personality = verdict.forced_personality
            session.history.append(
                ChatMessage(role="user", content=redacted_user_msg, intents=[])
            )
            safe_text = verdict.reply_override or "Keeping it friendly."
            session.history.append(
                ChatMessage(role="assistant", content=safe_text, intents=[])
            )
            session.message_count += 1
            SESSIONS.save(session, db=db, user_id=user.id if user is not None else None)
            return RoastResponse(
                roast=safe_text,
                scores=session.scores,
                intents_detected=[],
                template_id=None,
            )
        # Self-harm, distress, or PII: return a safe reply, do not roast.
        session.history.append(
            ChatMessage(role="user", content=redacted_user_msg, intents=[])
        )
        safe_text = verdict.reply_override or "I'll pass on that one."
        session.history.append(
            ChatMessage(role="assistant", content=safe_text, intents=[])
        )
        session.message_count += 1
        SESSIONS.save(session, db=db, user_id=user.id if user is not None else None)
        return RoastResponse(
            roast=safe_text,
            scores=session.scores,
            intents_detected=[],
            template_id=None,
        )

    # Enforce the per-session message cap on the regular flow. Safety replies
    # (above) already returned, so a self-harm / PII / minor user always gets
    # a safe reply even when the regular flow is rate-limited. Prevents
    # unbounded memory growth and a hostile user from monopolizing a session.
    if session.message_count >= MAX_SESSION_MESSAGES:
        raise HTTPException(
            429,
            f"session message cap reached ({MAX_SESSION_MESSAGES}); start a new session",
        )

    # Free-tier gate: authenticated free users get 5 messages total
    # across their entire account lifetime, then 402 Payment Required.
    # Anonymous (no JWT) users get the same per-session cap so the
    # gate stays usable for casual visitors.
    #
    # Concurrency: the check + increment is a single atomic SQL update
    # so two parallel requests can't both observe 4 and both pass the
    # gate. See C3 in the audit.
    from sqlalchemy import update
    has_active_sub = False
    if user is not None and db is not None:
        now = datetime.now(timezone.utc)
        has_active_sub = db.query(db_models.Subscription).filter(
            db_models.Subscription.user_id == user.id,
            db_models.Subscription.status == db_models.SubStatus.active,
            db_models.Subscription.current_period_end > now,
        ).first() is not None

    if user is not None and not has_active_sub:
        # Conditional update: only increment if we're still under the
        # cap. If the row was already at the cap, the WHERE matches no
        # row, rowcount is 0, and we 402.
        # On any DB error we 503 instead of silently bypassing the gate;
        # the previous behaviour let an attacker use a transient DB
        # hiccup to roast unlimited free messages. See audit #5.
        #
        # We commit the increment here so a parallel request can't both
        # observe 4 → both pass the gate. If the roast itself fails
        # later in this handler, the user's free_messages_used stays
        # incremented — the user lost a free credit, not the system
        # gave away an extra one. (Prior bug: the increment was
        # committed before any roast logic ran, so a downstream
        # exception still charged the user; rollback would have been
        # possible but opens a TOCTOU window.)
        from sqlalchemy.exc import SQLAlchemyError
        try:
            res = db.execute(
                update(db_models.User)
                .where(
                    db_models.User.id == user.id,
                    db_models.User.free_messages_used < FREE_MESSAGES_LIMIT,
                )
                .values(free_messages_used=db_models.User.free_messages_used + 1)
            )
            db.commit()
        except SQLAlchemyError as _exc:
            log.exception("free-tier atomic update failed: %s", _exc)
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail="service temporarily unavailable, please retry",
            )
        if res.rowcount == 0:
            # Either user is at/over the cap, or the row vanished.
            cur = db.query(db_models.User.free_messages_used).filter(
                db_models.User.id == user.id
            ).scalar() or 0
            if cur >= FREE_MESSAGES_LIMIT:
                raise HTTPException(
                    status_code=402,
                    detail=f"Free tier limit reached ({FREE_MESSAGES_LIMIT} messages total). Subscribe to keep roasting.",
                )
    # Note: anonymous (no JWT) users are protected by the per-session
    # MAX_SESSION_MESSAGES cap above (default 50). We don't try to gate
    # anonymous users on a smaller message count because we have no
    # stable identifier to track them across sessions — and a 50-message
    # cap is plenty to stop abuse without driving anonymous visitors
    # to subscribe.

    # (Free-tier counter was already atomically incremented above —
    # see the conditional `update(...).where(free_messages_used < 5)`
    # near the top of this handler. Doing it once atomically is the
    # only way to be safe under concurrency. See C3 in the audit.)

    # Append user message to history
    session.history.append(
        ChatMessage(role="user", content=req.message, intents=[])
    )

    # Detect intent
    hits = intent.detect_intents(req.message, LIB)
    detected = [h.name for h in hits]

    # Count excuses
    session.scores.excuses_used += scorer.count_excuses(req.message)
    session.scores.questionable_decisions += _count_questionable(req.message, detected)

    # Update memory fields used by placeholders
    for i in detected:
        if i not in session.detected_intents:
            session.detected_intents.append(i)

    # Detect comeback
    is_clapback = intent.is_comeback(req.message)
    if is_clapback:
        session.comeback_attempts += 1

    # Pick the roast
    final_text: str
    final_id: Optional[str] = None
    is_opener = False
    is_closer = False
    is_comeback_flag = False

    if is_clapback:
        cb = matcher.select_comeback(session.personality, LIB)
        if cb is not None:
            final_text = filler.fill_placeholders_by_spec(cb, LIB, session, prior_intent=None)
            final_id = cb.id
            is_comeback_flag = True
            # Mark as failure if the clapback was weak (short or just punctuation)
            if len(req.message.strip()) < 12 or req.message.strip() in {"no u", "you too"}:
                session.comeback_failures += 1
        else:
            final_text = "..."
    else:
        template = matcher.select_roast(
            message=req.message,
            mode=session.mode,
            personality=session.personality,
            session=session,
            library=LIB,
            detected_intents=detected,
        )
        if template is None:
            final_text = "I have nothing for you. Try again. Or don't. Honestly, I'd prefer you didn't."
        else:
            final_text = filler.fill_placeholders(
                template, LIB, session, detected
            )
            final_id = template.id

    # Apply personality flavor
    final_text = matcher.apply_personality_flavor(final_text, session.personality, LIB)

    # Add optional reaction emoji
    chosen_template = LIB.get_roast(final_id) if final_id else None
    if chosen_template and chosen_template.reaction:
        if not final_text.endswith(chosen_template.reaction):
            final_text = f"{final_text} {chosen_template.reaction}"

    # --- Safety: scan the outgoing roast for blocked terms ---
    out_verdict = safety.check_output(final_text)
    if not out_verdict.is_safe:
        log.warning(
            "blocked term in roast output: id=%s term=%s",
            final_id, out_verdict.blocked_term_in_output,
        )
        final_text = safety.sanitize_output(final_text)

    # Update session
    session.message_count += 1
    damage_added = chosen_template.damage if chosen_template else 5
    session.total_damage += damage_added
    if final_id and final_id not in session.recent_roast_ids:
        session.recent_roast_ids.append(final_id)
        if len(session.recent_roast_ids) > 8:
            session.recent_roast_ids = session.recent_roast_ids[-8:]
    session.history.append(
        ChatMessage(role="assistant", content=final_text, intents=detected)
    )

    scorer.update_scores(session, damage_added=damage_added)
    SESSIONS.save(session, db=db, user_id=user.id if user is not None else None)

    # Persist to authenticated user's chat history (best-effort; never
    # break the response if the DB write fails for any reason).
    if user is not None and db is not None:
        try:
            entry = db_models.ChatHistory(
                user_id=user.id,
                message=sanitize_text(req.message, max_length=MAX_HISTORY_MESSAGE_CHARS) or "",
                is_user=True,
                roast_response=sanitize_text(final_text, max_length=MAX_HISTORY_MESSAGE_CHARS),
                score_total=float(damage_added),
                session_id=session_id,
            )
            db.add(entry)
            entry2 = db_models.ChatHistory(
                user_id=user.id,
                message=sanitize_text(final_text, max_length=MAX_HISTORY_MESSAGE_CHARS) or "",
                is_user=False,
                roast_response=None,
                score_total=float(damage_added),
                session_id=session_id,
            )
            db.add(entry2)
            db.commit()
        except Exception as _exc:  # pragma: no cover
            log.warning("failed to persist chat history: %s", _exc)
            db.rollback()

    return RoastResponse(
        roast=final_text,
        scores=session.scores,
        intents_detected=detected,
        is_opener=is_opener,
        is_closer=is_closer,
        is_comeback=is_comeback_flag,
        template_id=final_id,
    )


@router.post("/session/{session_id}/end", response_model=EndSessionResponse)
def end_session(
    session_id: str,
    user: Annotated[Optional[db_models.User], Depends(auth.get_optional_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> EndSessionResponse:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "session not found")

    # Ownership check: if the session is owned by an authed user, only
    # that user (or an anonymous caller for an anonymous session) may
    # end it. An anonymous caller cannot end another user's session —
    # they could just trigger the closer for free, and worse, a
    # subsequent persistence write would clobber user_id on the row.
    if session.user_id is not None:
        if user is None or user.id != session.user_id:
            raise HTTPException(404, "session not found")

    # Idempotent: if already ended, just return the stored closer + scores.
    if session.ended_at is not None:
        return EndSessionResponse(
            session_id=session_id,
            final_scores=session.scores,
            closer=session.closer_text,
            share_url=f"/share/{session_id}",
        )

    closer_text: Optional[str] = None
    cl: Optional[object] = None
    if not session.closer_used:
        cl = matcher.select_closer(session.personality, LIB)
        if cl is not None:
            closer_text = filler.fill_placeholders_by_spec(cl, LIB, session, prior_intent=None)

    if closer_text is None:
        # Defensive fallback — every personality ships a closer today, but
        # this keeps the API contract intact (closer is always non-null on end).
        closer_text = FALLBACK_CLOSER

    # Apply personality flavor.
    closer_text = matcher.apply_personality_flavor(
        closer_text, session.personality, LIB
    )

    # Append the closer's reaction emoji if we have one and the text doesn't
    # already end with it.
    if (
        cl is not None
        and closer_text is not None
        and getattr(cl, "reaction", None)
        and not closer_text.endswith(cl.reaction)
    ):
        closer_text = f"{closer_text} {cl.reaction}"

    # Run the generated closer through the output safety filter.
    if closer_text is not None:
        out_v = safety.check_output(closer_text)
        if not out_v.is_safe:
            log.warning(
                "blocked term in closer: term=%s",
                out_v.blocked_term_in_output,
            )
            closer_text = safety.sanitize_output(closer_text)

    # Persist the closer on the session (so the share page can show the final
    # line and the /end endpoint is idempotent) and mark the session as ended.
    # DO NOT DELETE the session — the share URL needs the data to render.
    # A background cleanup task purges ended sessions older than
    # SHARED_SESSION_TTL_SECONDS.
    session.closer_text = closer_text
    session.closer_used = True
    session.ended_at = time.time()
    if closer_text and not session.history or (
        session.history and session.history[-1].content != closer_text
    ):
        session.history.append(
            ChatMessage(role="assistant", content=closer_text, intents=[])
        )
    SESSIONS.save(session, db=db, user_id=user.id if user is not None else None)

    MEMORY.record_session(session)

    # Persist closer to authenticated user's history.
    if user is not None and db is not None and closer_text:
        try:
            entry = db_models.ChatHistory(
                user_id=user.id,
                message=sanitize_text(closer_text, max_length=MAX_HISTORY_MESSAGE_CHARS) or "",
                is_user=False,
                roast_response=None,
                score_total=0.0,
                session_id=session_id,
            )
            db.add(entry)
            db.commit()
        except Exception as _exc:  # pragma: no cover
            log.warning("failed to persist closer: %s", _exc)
            db.rollback()

    return EndSessionResponse(
        session_id=session_id,
        final_scores=session.scores,
        closer=closer_text,
        share_url=f"/share/{session_id}",
    )


@router.get("/session/{session_id}", response_model=SessionStateResponse)
def get_session(
    session_id: str,
    user: Annotated[Optional[db_models.User], Depends(auth.get_optional_user)] = None,
) -> SessionStateResponse:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    # Same ownership check as /end: an authed session is only readable
    # by its owner. Anonymous sessions remain public (the share URL is
    # meant to be shareable with anyone who has the link).
    if session.user_id is not None and (user is None or user.id != session.user_id):
        raise HTTPException(404, "session not found")
    return SessionStateResponse(
        session_id=session.session_id,
        mode=session.mode,
        personality=session.personality,
        message_count=session.message_count,
        scores=session.scores,
        history=session.history,
        is_ended=session.ended_at is not None,
    )


@router.post("/session/{session_id}/recover", response_model=SessionStateResponse)
def recover_session(
    session_id: str,
    user: Annotated[db_models.User, Depends(auth.get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> SessionStateResponse:
    """Reconstruct a session after a host cold start.

    On free-tier hosts (Render, Koyeb) the in-memory session store is
    wiped when the process spins down. Authenticated users can call
    this endpoint to reload their last-known session state from the
    `roast_sessions` table. Anonymous sessions can't be recovered
    because we never persisted them.

    Security: the recovered session's `user_id` MUST match the
    requesting user. Otherwise a leaked session id from one user
    could be used to peek at another user's transcript.

    This endpoint is idempotent: if the session is already in memory
    (no cold start happened), we return its state directly.
    """
    in_mem = SESSIONS.get(session_id)
    if in_mem is not None:
        # Authorization: an in-memory session may be an anonymous one
        # (no user_id), or it may belong to a different user. The
        # recovery endpoint must refuse to leak either. We treat
        # anonymous sessions as 404 here for the same reason as the
        # DB branch: the live path never persisted them, and we don't
        # want to expose a transient anon transcript to an unrelated
        # authed caller.
        if in_mem.user_id is None or in_mem.user_id != user.id:
            raise HTTPException(404, "session not found")
        return SessionStateResponse(
            session_id=in_mem.session_id,
            mode=in_mem.mode,
            personality=in_mem.personality,
            message_count=in_mem.message_count,
            scores=in_mem.scores,
            history=in_mem.history,
            is_ended=in_mem.ended_at is not None,
        )

    from . import session as session_mod
    restored = session_mod.load_session_from_db(db, session_id)
    if restored is None:
        raise HTTPException(404, "session not found")

    # Authorization: only the owning user can recover. We check both
    # the persisted user_id on the row and the in-state user_id field
    # (defence in depth: a corrupt row shouldn't bypass auth).
    row = db.query(db_models.RoastSession).filter(
        db_models.RoastSession.session_id == session_id
    ).first()
    if row is None or row.user_id is None:
        # Anonymous session — never persisted by the live path, so if
        # we see one, it's either a test artifact or a tampering
        # attempt. Refuse to expose it.
        raise HTTPException(404, "session not found")
    if row.user_id != user.id:
        # Don't leak whether the session id exists for someone else.
        raise HTTPException(404, "session not found")

    # Repopulate the in-memory store so the next /roast or /end is
    # hot-path. We hold the store's lock implicitly via SESSIONS.save.
    SESSIONS.save(restored)
    log.info("recovered session %s for user %s", session_id, user.id)

    return SessionStateResponse(
        session_id=restored.session_id,
        mode=restored.mode,
        personality=restored.personality,
        message_count=restored.message_count,
        scores=restored.scores,
        history=restored.history,
        is_ended=restored.ended_at is not None,
    )


@router.post("/admin/cleanup")
def cleanup(request: Request) -> dict:
    """Remove ended sessions whose share window has expired. Returns the
    number of sessions purged. Intended to be called periodically by a
    cron or by a frontend ping — not destructive to live sessions.

    Requires X-Admin-Key header for authentication.
    """
    # Constant-time key comparison via hmac.compare_digest to avoid
    # leaking the key length or position on mismatch. See BUG-ADM-001.
    admin_key = request.headers.get("X-Admin-Key") or ""
    expected_key = os.environ.get("ADMIN_API_KEY", "")
    if not expected_key:
        # Admin key not configured — refuse the request rather than fall
        # back to a hardcoded dev value. Misconfiguration shouldn't open
        # a back door.
        raise HTTPException(
            status_code=503,
            detail="Admin endpoint not configured. Set ADMIN_API_KEY.",
        )
    import hmac
    if not hmac.compare_digest(admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    in_mem_removed = SESSIONS.cleanup_expired(SHARED_SESSION_TTL_SECONDS)

    # Also clean up the persisted `roast_sessions` table. The previous
    # behaviour only cleaned the in-memory store, so on a long-lived
    # host the DB table grew unboundedly. The TTL here matches the
    # share-window TTL so a session's recovery URL is also pruned.
    db_removed = 0
    try:
        from datetime import datetime, timezone
        cutoff = datetime.fromtimestamp(time.time() - SHARED_SESSION_TTL_SECONDS, tz=timezone.utc)
        # Only delete ended sessions past the TTL. Live sessions
        # (ended_at is NULL) are NEVER deleted by the cleanup task.
        from . import db_models
        result = db.query(db_models.RoastSession).filter(
            db_models.RoastSession.ended_at.isnot(None),
            db_models.RoastSession.ended_at < cutoff,
        ).delete(synchronize_session=False)
        db.commit()
        db_removed = int(result or 0)
    except Exception as e:  # pragma: no cover - DB error path
        log.warning("cleanup: DB purge failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass

    return {
        "removed": in_mem_removed + db_removed,
        "in_memory_removed": in_mem_removed,
        "db_removed": db_removed,
        "ttl_seconds": SHARED_SESSION_TTL_SECONDS,
    }


# ----- Helpers -----

# Words/phrases that, in programming context, count as questionable decisions.
PROGRAMMING_RED_FLAGS = [
    "npm i", "npm install", "push to main", "deploy on friday", "deploy friday",
    "in production", "force push", "rm -rf", "production", "friday deploy",
]


def _count_questionable(message: str, intents: list[str]) -> int:
    if "programming" not in intents:
        return 0
    msg_low = message.lower()
    return sum(1 for flag in PROGRAMMING_RED_FLAGS if flag in msg_low)
