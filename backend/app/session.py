"""Session and user memory management.

`SessionStore` and `UserMemory` are the in-memory hot path. For
authenticated users, `SessionStore.save()` also writes the session
state to the `roast_sessions` table so the user can resume after the
process restarts (free-tier hosts spin down after 15 minutes of idle).

Anonymous sessions are NOT persisted: they have no user_id to
associate with and their lifetime is short by design.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from threading import RLock
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    ChatMessage,
    Personality,
    RoastMode,
    Session,
    SessionScores,
)
from .scorer import fresh_scores

log = logging.getLogger(__name__)


# Caps to keep in-memory state bounded under abuse. Sessions already have
# a TTL-based cleanup path (cleanup_expired); the cap is the second line
# of defence. UserMemory has no TTL — the cap is the only thing that
# stops a hostile client from filling memory with unique usernames.
MAX_SESSIONS = int(os.environ.get("ROASTGPT_MAX_SESSIONS", "10000"))
MAX_MEM_USERS = int(os.environ.get("ROASTGPT_MAX_MEM_USERS", "10000"))


# ----- Session store -----


def session_to_persisted(session: Session, user_id: Optional[int]) -> dict:
    """Serialise a Session into a JSON-safe dict for the roast_sessions
    table. Round-trips back via session_from_persisted."""
    return {
        "version": 1,
        "session_id": session.session_id,
        "username": session.username,
        "roaster_gender": session.roaster_gender,
        "mode": session.mode.value if hasattr(session.mode, "value") else session.mode,
        "personality": session.personality.value if hasattr(session.personality, "value") else session.personality,
        "created_at": session.created_at,
        "message_count": session.message_count,
        "total_damage": session.total_damage,
        "comeback_attempts": session.comeback_attempts,
        "comeback_failures": session.comeback_failures,
        "scores": session.scores.model_dump(),
        "history": [m.model_dump() for m in session.history],
        "recent_roast_ids": list(session.recent_roast_ids),
        "detected_intents": list(session.detected_intents),
        "opener_used": session.opener_used,
        "closer_used": session.closer_used,
        "ended_at": session.ended_at,
        "closer_text": session.closer_text,
        "user_id": user_id,
    }


def session_from_persisted(data: dict) -> Session:
    """Inverse of session_to_persisted. Restores a Session from a JSON
    dict read from the roast_sessions table."""
    return Session(
        session_id=data["session_id"],
        username=data.get("username"),
        user_id=data.get("user_id"),
        roaster_gender=data.get("roaster_gender"),
        mode=RoastMode(data["mode"]),
        personality=Personality(data["personality"]),
        created_at=float(data["created_at"]),
        message_count=int(data.get("message_count", 0)),
        total_damage=int(data.get("total_damage", 0)),
        comeback_attempts=int(data.get("comeback_attempts", 0)),
        comeback_failures=int(data.get("comeback_failures", 0)),
        scores=SessionScores.model_validate(data.get("scores") or {}),
        history=[ChatMessage.model_validate(m) for m in (data.get("history") or [])],
        recent_roast_ids=list(data.get("recent_roast_ids") or []),
        detected_intents=list(data.get("detected_intents") or []),
        opener_used=bool(data.get("opener_used", False)),
        closer_used=bool(data.get("closer_used", False)),
        ended_at=data.get("ended_at"),
        closer_text=data.get("closer_text"),
    )


def _persist_session(db: Session, session: Session, user_id: int) -> None:
    """Upsert a session row. Best-effort: any error is logged and
    swallowed so a transient DB problem can't break the live request.

    Uses the request's DB session inside a SAVEPOINT (nested
    transaction). A failure here only rolls back the savepoint, not
    the request handler's own transaction. Two concurrent /roast or
    /end calls for the same session are serialised by `with_for_update`
    on SQLite, or by the unique constraint + `ON CONFLICT DO UPDATE`
    on PostgreSQL.
    """
    # Lazy imports: avoid a circular import at module load.
    from . import db_models

    try:
        state = session_to_persisted(session, user_id=user_id)
        values = dict(
            session_id=session.session_id,
            user_id=user_id,
            mode=state["mode"],
            personality=state["personality"],
            username=state.get("username"),
            roaster_gender=state.get("roaster_gender"),
            state_json=state,
            ended_at=session.ended_at,
        )

        bind = db.get_bind()
        # Use a savepoint so a DB error here only rolls back the
        # persist, not the request handler's own in-flight writes.
        # SQLAlchemy exposes this as `db.begin_nested()`.
        with db.begin_nested():
            if bind.dialect.name == "postgresql":
                # Native upsert: atomic INSERT-or-UPDATE in one round
                # trip. Two concurrent /roast calls for the same
                # session don't race because the unique constraint
                # serialises the conflict resolution.
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(db_models.RoastSession).values(**values)
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in db_models.RoastSession.__table__.columns
                    if c.name not in ("id", "created_at")
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=[db_models.RoastSession.session_id],
                    set_=update_cols,
                )
                db.execute(stmt)
            else:
                # SQLite (tests + dev fallback). Lock the existing row
                # for the duration of the transaction so a parallel
                # writer waits. If no row exists, insert.
                row = db.query(db_models.RoastSession).filter(
                    db_models.RoastSession.session_id == session.session_id
                ).with_for_update(read=False).first()
                if row is None:
                    db.add(db_models.RoastSession(**values))
                else:
                    for k, v in values.items():
                        setattr(row, k, v)
                db.flush()
    except Exception as e:  # pragma: no cover - DB error path
        log.warning("failed to persist session %s: %s", session.session_id, e)
        # The savepoint has already been rolled back by the
        # `with` block. Don't re-raise: this is best-effort.


def load_session_from_db(db: Session, session_id: str) -> Optional[Session]:
    """Read a session row from the DB and reconstruct the in-memory
    `Session` object. Returns None if not found."""
    try:
        from . import db_models
        row = db.query(db_models.RoastSession).filter(
            db_models.RoastSession.session_id == session_id
        ).first()
    except Exception as e:  # pragma: no cover
        log.warning("failed to read session %s: %s", session_id, e)
        return None
    if row is None or not row.state_json:
        return None
    try:
        return session_from_persisted(row.state_json)
    except Exception as e:  # pragma: no cover
        log.warning("corrupt session state %s: %s", session_id, e)
        return None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = RLock()

    def create(
        self,
        mode: RoastMode,
        personality: Personality,
        username: Optional[str],
        roaster_gender: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Session:
        sid = uuid.uuid4().hex  # 128 bits; was uuid4().hex[:12] (48 bits)
        s = Session(
            session_id=sid,
            username=username,
            user_id=user_id,
            roaster_gender=roaster_gender,
            mode=mode,
            personality=personality,
            created_at=time.time(),
            scores=fresh_scores(),
        )
        with self._lock:
            # If we're at the cap, try to evict ended sessions first.
            # Live sessions are NEVER evicted — losing a live
            # conversation mid-flight (the previous behaviour) was a
            # real data-loss bug. If we can't make room by evicting
            # ended sessions, refuse the new one with a 503 to the
            # caller (handled at the route level).
            if len(self._sessions) >= MAX_SESSIONS:
                self._evict_oldest_ended()
            if len(self._sessions) >= MAX_SESSIONS:
                # Still at cap — every existing session is live. The
                # service is at capacity. We could either:
                #   (a) refuse the new session (return None; the route
                #       should map this to 503)
                #   (b) silently evict the oldest live session (loses
                #       user state — DO NOT DO THIS)
                # We pick (a). Set a session-overflow flag the route
                # can check.
                self._overflow = True
                return None  # type: ignore[return-value]
            self._overflow = False
            self._sessions[sid] = s
        return s

    @property
    def overflow(self) -> bool:
        """True if the most recent `create()` was refused due to the
        cap being reached by live sessions. The route maps this to 503.
        """
        return getattr(self, "_overflow", False)

    def _evict_oldest_ended(self) -> None:
        """Evict the single oldest ended session. Caller holds the lock."""
        ended = [
            (s.created_at, sid)
            for sid, s in self._sessions.items()
            if s.ended_at is not None
        ]
        if not ended:
            return
        ended.sort()
        _, victim = ended[0]
        self._sessions.pop(victim, None)

    def get(self, sid: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(sid)

    def save(
        self,
        session: Session,
        *,
        db: Optional[Session] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """Save to in-memory store, and (if `db` and `user_id` are
        provided) upsert into the roast_sessions table.

        The DB write is best-effort. Callers in the request path can
        pass `db` from FastAPI's dependency and `user_id` from the
        authenticated user, and the session survives a cold start.
        """
        with self._lock:
            self._sessions[session.session_id] = session
        if db is not None and user_id is not None:
            _persist_session(db, session, user_id=user_id)

    def delete(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)

    def cleanup_expired(self, max_age_seconds: float) -> int:
        """Remove ended sessions older than `max_age_seconds`. Returns the
        number of sessions removed. Active sessions are never removed."""
        now = time.time()
        removed = 0
        with self._lock:
            for sid in list(self._sessions.keys()):
                s = self._sessions[sid]
                if s.ended_at is not None and (now - s.ended_at) > max_age_seconds:
                    del self._sessions[sid]
                    removed += 1
        return removed


# ----- User memory store -----

class UserMemory:
    """Long-term per-user state. Used for callbacks and analytics."""

    def __init__(self) -> None:
        self._mem: dict[str, dict] = {}
        self._last_used: dict[str, float] = {}
        self._lock = RLock()

    def record_session(self, session: Session) -> None:
        if not session.username:
            return
        with self._lock:
            existing = self._mem.get(session.username, {})
            totals = existing.get("totals", {"sessions": 0, "roasts": 0})
            totals["sessions"] += 1
            totals["roasts"] += session.scores.reality_checks

            intent_counter = existing.get("intent_counter", {})
            for intent in session.detected_intents:
                intent_counter[intent] = intent_counter.get(intent, 0) + 1
            recurring = max(intent_counter, key=intent_counter.get) if intent_counter else None

            self._mem[session.username] = {
                "username":       session.username,
                "totals":         totals,
                "favorite_mode":  existing.get("favorite_mode", session.mode.value),
                "last_topic":     session.detected_intents[-1] if session.detected_intents else None,
                "last_damage":    session.scores.emotional_damage,
                "recurring_topic": recurring,
                "last_session_at": time.time(),
            }
            self._last_used[session.username] = time.time()
            # Evict the least-recently-active user when over the cap.
            self._evict_lru_if_full()

    def _evict_lru_if_full(self) -> None:
        if len(self._mem) <= MAX_MEM_USERS:
            return
        victim = min(self._last_used, key=self._last_used.get)  # type: ignore[arg-type]
        self._mem.pop(victim, None)
        self._last_used.pop(victim, None)

    def get(self, username: str) -> Optional[dict]:
        with self._lock:
            mem = self._mem.get(username)
            if mem is not None:
                self._last_used[username] = time.time()
            return dict(mem) if mem else None


SESSIONS = SessionStore()
MEMORY = UserMemory()
