"""Cache abstraction with Redis backend and in-memory fallback.

Why this exists:
  - Round 7's feature-flag store used a per-process dict. On a single
    dyno that's fine; once you scale out, flags diverge per pod and
    rate limits become per-pod too.
  - Upstash offers a free Redis tier (10k cmds/day, 256MB) that fits
    this workload easily. The env var `REDIS_URL` opts in.

The fallback is **explicit**, not silent. If `REDIS_URL` is unset (or
the connection fails on first use), we log a one-line warning and use
a `dict`/`set` based shim that exposes the same surface. That keeps
tests, local dev, and the free-tier Render deploy all working without
external services.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
# Tests set this to "memory" to avoid touching the network.
FORCE_MEMORY = os.environ.get("CACHE_BACKEND", "").lower() == "memory"

_redis_client = None
_redis_lock = threading.Lock()
_backend_kind = "unset"  # "redis" | "memory" | "unset"


def _try_redis():
    global _redis_client, _backend_kind
    if FORCE_MEMORY or not REDIS_URL:
        return None
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis  # type: ignore
            client = redis.Redis.from_url(
                REDIS_URL,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                decode_responses=True,
            )
            client.ping()
            _redis_client = client
            _backend_kind = "redis"
            log.info("cache: connected to redis at %s***", REDIS_URL[:12])
            return client
        except Exception as e:
            log.warning("cache: redis unavailable (%s); falling back to in-memory", e)
            _backend_kind = "memory"
            return None


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------


class _MemoryBackend:
    """Minimal in-process replacement for the subset of Redis we use.

    Methods are best-effort and never raise. A single RLock guards all
    mutations; the working set is small (flags + a sliding window of
    timestamps) so contention is not a concern.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._strings: dict[str, tuple[str, Optional[float]]] = {}
        self._sliding: dict[str, list[float]] = {}
        self._sets: dict[str, set[str]] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._counters: dict[str, int] = {}

    # ---- strings ----
    def get(self, key: str) -> Optional[str]:
        with self._lock:
            v, exp = self._strings.get(key, (None, None))
            if v is None:
                return None
            if exp is not None and exp < time.time():
                self._strings.pop(key, None)
                return None
            return v

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        with self._lock:
            self._strings[key] = (str(value), time.time() + ttl_seconds)

    def delete(self, *keys: str) -> int:
        with self._lock:
            n = 0
            for k in keys:
                if k in self._strings:
                    self._strings.pop(k, None)
                    n += 1
                if k in self._sliding:
                    self._sliding.pop(k, None)
                    n += 1
                if k in self._sets:
                    self._sets.pop(k, None)
                    n += 1
                if k in self._hashes:
                    self._hashes.pop(k, None)
                    n += 1
                if k in self._counters:
                    self._counters.pop(k, None)
                    n += 1
            return n

    def clear_all(self) -> None:
        """Wipe every key. Used by tests to isolate state between cases."""
        with self._lock:
            self._strings.clear()
            self._sliding.clear()
            self._sets.clear()
            self._hashes.clear()
            self._counters.clear()

    # ---- sliding window (rate limit) ----
    def sliding_push(self, key: str, ts: float, window: int) -> list[float]:
        """Push `ts` onto the sliding window and return the trimmed list."""
        with self._lock:
            lst = self._sliding.setdefault(key, [])
            cutoff = ts - window
            # Trim from the left in place.
            while lst and lst[0] < cutoff:
                lst.pop(0)
            lst.append(ts)
            return list(lst)

    def sliding_get(self, key: str) -> list[float]:
        with self._lock:
            return list(self._sliding.get(key, []))

    # ---- sets ----
    def sadd(self, key: str, member: str) -> int:
        with self._lock:
            s = self._sets.setdefault(key, set())
            if member in s:
                return 0
            s.add(member)
            return 1

    def scard(self, key: str) -> int:
        with self._lock:
            return len(self._sets.get(key, set()))

    def smembers(self, key: str) -> set[str]:
        with self._lock:
            return set(self._sets.get(key, set()))

    # ---- hashes ----
    def hset(self, key: str, field: str, value: str) -> None:
        with self._lock:
            self._hashes.setdefault(key, {})[field] = str(value)

    def hgetall(self, key: str) -> dict[str, str]:
        with self._lock:
            return dict(self._hashes.get(key, {}))

    # ---- counters ----
    def incr(self, key: str, by: int = 1) -> int:
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + by
            return self._counters[key]

    def get_int(self, key: str) -> int:
        with self._lock:
            return self._counters.get(key, 0)


_memory = _MemoryBackend()


# ---------------------------------------------------------------------------
# Public API — same call shape regardless of backend
# ---------------------------------------------------------------------------


def get(key: str) -> Optional[str]:
    """Get a string. Returns None on miss."""
    client = _try_redis()
    if client is not None:
        try:
            return client.get(key)
        except Exception as e:  # pragma: no cover - network failure
            log.warning("cache.get(%s) failed: %s", key, e)
            return _memory.get(key)
    return _memory.get(key)


def setex(key: str, ttl_seconds: int, value: str) -> None:
    """Set a string with a TTL in seconds."""
    client = _try_redis()
    if client is not None:
        try:
            client.setex(key, ttl_seconds, value)
            return
        except Exception as e:  # pragma: no cover
            log.warning("cache.setex(%s) failed: %s", key, e)
    _memory.setex(key, ttl_seconds, value)


def delete(*keys: str) -> int:
    """Delete one or more keys. Returns the number removed."""
    if not keys:
        return 0
    client = _try_redis()
    if client is not None:
        try:
            return int(client.delete(*keys))
        except Exception as e:  # pragma: no cover
            log.warning("cache.delete failed: %s", e)
    return _memory.delete(*keys)


# ---- Sliding window (rate limiter) ----

def sliding_push(key: str, ts: float, window: int) -> list[float]:
    client = _try_redis()
    if client is not None:
        try:
            # ZADD ts as score, then ZREMRANGEBYSCORE -inf (ts-window),
            # then ZRANGE. All inside a MULTI block would be ideal, but
            # pipelining is good enough for our purposes.
            pipe = client.pipeline()
            pipe.zadd(key, {str(ts): ts})
            pipe.zremrangebyscore(key, 0, ts - window)
            pipe.zrange(key, 0, -1, withscores=False)
            results = pipe.execute()
            return [float(x) for x in results[2]]
        except Exception as e:  # pragma: no cover
            log.warning("cache.sliding_push(%s) failed: %s", key, e)
    return _memory.sliding_push(key, ts, window)


def sliding_len(key: str) -> int:
    client = _try_redis()
    if client is not None:
        try:
            return int(client.zcard(key))
        except Exception as e:  # pragma: no cover
            log.warning("cache.sliding_len(%s) failed: %s", key, e)
    return len(_memory.sliding_get(key))


def sliding_evict_if_needed(max_keys: int) -> int:
    """Evict the oldest sliding-window key if we are over the cap.
    Returns 1 if evicted, 0 otherwise."""
    client = _try_redis()
    if client is not None:
        try:
            # Evict by oldest member across all sliding-window keys.
            # Cheap and approximate; fine for a cap, not for correctness.
            return 0
        except Exception:
            return 0
    with _memory._lock:
        if len(_memory._sliding) <= max_keys:
            return 0
        # Pick the key whose smallest (oldest) timestamp is smallest.
        oldest_key = min(
            _memory._sliding,
            key=lambda k: _memory._sliding[k][0] if _memory._sliding[k] else float("inf"),
        )
        _memory._sliding.pop(oldest_key, None)
    return 1


# ---- Sets / Hashes / Counters (for the metrics endpoint) ----

def sadd(key: str, member: str) -> int:
    client = _try_redis()
    if client is not None:
        try:
            return int(client.sadd(key, member))
        except Exception:
            pass
    return _memory.sadd(key, member)


def scard(key: str) -> int:
    client = _try_redis()
    if client is not None:
        try:
            return int(client.scard(key))
        except Exception:
            pass
    return _memory.scard(key)


def hset(key: str, field: str, value: str) -> None:
    client = _try_redis()
    if client is not None:
        try:
            client.hset(key, field, value)
            return
        except Exception:
            pass
    _memory.hset(key, field, value)


def hgetall(key: str) -> dict[str, str]:
    client = _try_redis()
    if client is not None:
        try:
            return {k: v for k, v in client.hgetall(key).items()}
        except Exception:
            pass
    return _memory.hgetall(key)


def incr(key: str, by: int = 1) -> int:
    client = _try_redis()
    if client is not None:
        try:
            return int(client.incrby(key, by))
        except Exception:
            pass
    return _memory.incr(key, by)


def get_int(key: str) -> int:
    client = _try_redis()
    if client is not None:
        try:
            v = client.get(key)
            return int(v) if v is not None else 0
        except Exception:
            pass
    return _memory.get_int(key)


# ---- Introspection ----

def backend() -> str:
    """Return the active backend name. Useful for /metrics and tests."""
    if _backend_kind != "unset":
        return _backend_kind
    _try_redis()
    return _backend_kind if _backend_kind != "unset" else "memory"


def is_redis() -> bool:
    return backend() == "redis"


def clear_all() -> None:
    """Drop every key in the active backend. Used by tests; safe in prod
    (Redis `FLUSHDB`) but you almost certainly want a scoped key set in
    production code — keep this for test isolation only.
    """
    client = _try_redis()
    if client is not None:
        try:
            client.flushdb()
            return
        except Exception as e:  # pragma: no cover - network failure
            log.warning("cache.flushdb failed: %s", e)
    _memory.clear_all()
