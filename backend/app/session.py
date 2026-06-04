"""Session and user memory management.

For MVP, both are in-memory dicts. Swap for Redis (sessions) and PostgreSQL
(memory) when moving to production.
"""
from __future__ import annotations

import os
import time
import uuid
from threading import RLock
from typing import Optional

from .models import (
    ChatMessage,
    Personality,
    RoastMode,
    Session,
    SessionScores,
)
from .scorer import fresh_scores


# Caps to keep in-memory state bounded under abuse. Sessions already have
# a TTL-based cleanup path (cleanup_expired); the cap is the second line
# of defence. UserMemory has no TTL — the cap is the only thing that
# stops a hostile client from filling memory with unique usernames.
MAX_SESSIONS = int(os.environ.get("ROASTGPT_MAX_SESSIONS", "10000"))
MAX_MEM_USERS = int(os.environ.get("ROASTGPT_MAX_MEM_USERS", "10000"))


# ----- Session store -----

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
    ) -> Session:
        sid = uuid.uuid4().hex  # 128 bits; was uuid4().hex[:12] (48 bits)
        s = Session(
            session_id=sid,
            username=username,
            roaster_gender=roaster_gender,
            mode=mode,
            personality=personality,
            created_at=time.time(),
            scores=fresh_scores(),
        )
        with self._lock:
            # If we're at the cap, evict the oldest ended session. Live
            # sessions are never evicted here; if the cap is reached by
            # active sessions only, refuse to create a new one.
            if len(self._sessions) >= MAX_SESSIONS:
                self._evict_oldest_ended()
            if len(self._sessions) >= MAX_SESSIONS:
                # Still at cap — too many live sessions. Drop a non-ended
                # session to keep the service responsive. We pick the
                # oldest live session.
                oldest_sid = min(
                    (s.session_id for s in self._sessions.values() if s.ended_at is None),
                    default=None,
                    key=lambda k: self._sessions[k].created_at,
                )
                if oldest_sid is not None:
                    self._sessions.pop(oldest_sid, None)
            self._sessions[sid] = s
        return s

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

    def save(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

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
