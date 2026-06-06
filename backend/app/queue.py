"""Background-job queue with Celery backend and in-process fallback.

Why this exists:
  - The free-tier Render web service is a single dyno with no separate
    worker. The Round 1-7 in-process scheduler (see `app/jobs.py`) is
    sufficient for that constraint, but it doesn't survive horizontal
    scaling: two pods would both run retention sweeps.
  - Celery is the standard, well-trodden path. Setting
    `CELERY_BROKER_URL=redis://...` opts in.

The fallback is identical to the previous behaviour: when no broker
is configured, `enqueue()` runs the job synchronously in a daemon
thread. Tests set `QUEUE_BACKEND=memory` to be deterministic and
non-blocking.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "").strip()
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "").strip()
FORCE_MEMORY = os.environ.get("QUEUE_BACKEND", "").lower() == "memory"

_celery_app = None
_backend_kind = "unset"  # "celery" | "memory" | "unset"


def _try_celery():
    global _celery_app, _backend_kind
    if FORCE_MEMORY or not CELERY_BROKER_URL:
        return None
    with threading.Lock():
        if _celery_app is not None:
            return _celery_app
        try:
            from celery import Celery  # type: ignore
            app = Celery(
                "roastgpt",
                broker=CELERY_BROKER_URL,
                backend=CELERY_RESULT_BACKEND or None,
            )
            # Sensible defaults for a low-volume worker.
            app.conf.update(
                task_acks_late=True,
                worker_prefetch_multiplier=1,
                task_serializer="json",
                accept_content=["json"],
                result_serializer="json",
                timezone="UTC",
                enable_utc=True,
            )
            _celery_app = app
            _backend_kind = "celery"
            log.info("queue: celery broker configured at %s***", CELERY_BROKER_URL[:12])
            return app
        except Exception as e:  # pragma: no cover - import/connect error
            log.warning("queue: celery init failed (%s); falling back to in-process", e)
            _backend_kind = "memory"
            return None


# ---------------------------------------------------------------------------
# In-process fallback: daemon-thread runner
# ---------------------------------------------------------------------------


class _MemoryQueue:
    """Drop-in replacement for the bits of Celery we touch.

    `send_task(name, args=...)` spawns a daemon thread that runs the
    function with try/except logging. We don't return a result; the
    caller doesn't await one (jobs are fire-and-forget by design).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, Callable[..., Any]] = {}
        self._submitted = 0
        self._failed = 0

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        with self._lock:
            self._tasks[name] = fn

    def send_task(self, name: str, args: Optional[tuple] = None,
                  kwargs: Optional[dict] = None) -> str:
        with self._lock:
            fn = self._tasks.get(name)
            self._submitted += 1
        if fn is None:
            log.warning("queue: no task registered for %s", name)
            return f"unregistered:{name}"
        t = threading.Thread(
            target=self._run, args=(fn, name, args or (), kwargs or {}),
            name=f"queue:{name}", daemon=True,
        )
        t.start()
        return f"thread:{name}:{t.ident}"

    def _run(self, fn, name, args, kwargs):
        try:
            fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failed += 1
            log.warning("queue: task %s failed:\n%s", name, traceback.format_exc())

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "submitted": self._submitted,
                "failed": self._failed,
                "registered": len(self._tasks),
            }


_memory = _MemoryQueue()


# ---------------------------------------------------------------------------
# Task registry — every background job is registered here once, so the
# same name is used by both backends.
# ---------------------------------------------------------------------------


TASKS: dict[str, Callable[..., Any]] = {}


def register_task(name: str, fn: Callable[..., Any]) -> None:
    """Register a task by name. Idempotent."""
    TASKS[name] = fn
    _memory.register(name, fn)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enqueue(name: str, *args: Any, **kwargs: Any) -> str:
    """Schedule a task. Returns a backend-specific handle (string)."""
    if name not in TASKS:
        # Lazy-register if the caller didn't bother. Keeps the call
        # sites short.
        fn = globals().get(name)
        if fn is not None and callable(fn):
            register_task(name, fn)
    app = _try_celery()
    if app is not None:
        try:
            r = app.send_task(name, args=args, kwargs=kwargs)
            return str(r.id)
        except Exception as e:  # pragma: no cover
            log.warning("queue.send_task(%s) failed: %s; running in-memory", name, e)
    return _memory.send_task(name, args, kwargs)


def enqueue_delay(name: str, delay_seconds: int, *args: Any, **kwargs: Any) -> str:
    """Schedule a task to run after `delay_seconds`. Only Celery supports
    this natively; the in-memory fallback just sleeps in a thread
    (the task itself is still async w.r.t. the caller)."""
    if delay_seconds <= 0:
        return enqueue(name, *args, **kwargs)
    app = _try_celery()
    if app is not None:
        try:
            r = app.send_task(name, args=args, kwargs=kwargs, countdown=delay_seconds)
            return str(r.id)
        except Exception as e:  # pragma: no cover
            log.warning("queue.enqueue_delay(%s) failed: %s", name, e)
    def _delayed():
        time.sleep(delay_seconds)
        _memory.send_task(name, args, kwargs)
    t = threading.Thread(target=_delayed, name=f"queue-delay:{name}", daemon=True)
    t.start()
    return f"thread-delayed:{name}"


def beat_register(name: str, schedule_seconds: int) -> None:
    """Register a periodic task. With Celery this requires a beat
    schedule (configured at deploy time); in memory we just spawn a
    timer thread that calls enqueue() on the cadence."""
    def _loop():
        while True:
            time.sleep(schedule_seconds)
            try:
                enqueue(name)
            except Exception:
                log.warning("beat: %s enqueue failed", name)
    t = threading.Thread(target=_loop, name=f"queue-beat:{name}", daemon=True)
    t.start()


def backend() -> str:
    if _backend_kind != "unset":
        return _backend_kind
    _try_celery()
    return _backend_kind if _backend_kind != "unset" else "memory"


def is_celery() -> bool:
    return backend() == "celery"


def stats() -> dict[str, Any]:
    """Return queue stats for /metrics."""
    out = {
        "backend": backend(),
        "memory": _memory.stats(),
    }
    return out
