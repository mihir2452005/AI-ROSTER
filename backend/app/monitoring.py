"""Monitoring & logging.

Sentry (errors, performance, releases) is initialised only when
SENTRY_DSN is set; otherwise the SDK no-ops. We also install a JSON
formatter on the root logger when LOG_FORMAT=json — useful for
shipping to Logtail / Datadog / Loki without writing a custom
formatter downstream.

Both knobs default to "off" so dev/test runs are silent and unchanged.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT", os.environ.get("ENVIRONMENT", "development"))
SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE", "roastgpt@0.1.0")
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
LOG_FORMAT = os.environ.get("LOG_FORMAT", "text").lower()  # "text" or "json"

_initialised = False


class _JsonFormatter(logging.Formatter):
    """Compact JSON line per record. Keys are stable for downstream
    parsers (Datadog, Logtail, Loki)."""

    # Standard `LogRecord` attributes we don't want to dump in full.
    _SKIP = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Extras (anything attached via `logger.info("msg", extra={...})`).
        for k, v in record.__dict__.items():
            if k in self._SKIP or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except TypeError:
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def init_sentry() -> None:
    """Initialise the Sentry SDK. Safe to call multiple times."""
    global _initialised
    if _initialised:
        return
    if not SENTRY_DSN:
        log.info("monitoring: SENTRY_DSN unset; Sentry disabled")
        _init_logging()
        _initialised = True
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENVIRONMENT,
            release=SENTRY_RELEASE,
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            # Don't send PII. The DSN is project-scoped and we don't
            # want emails/IPs in the payload by default.
            send_default_pii=False,
        )
        log.info("monitoring: Sentry initialised (env=%s, release=%s)", SENTRY_ENVIRONMENT, SENTRY_RELEASE)
    except Exception as e:
        log.warning("monitoring: Sentry init failed (%s); continuing without it", e)
    _init_logging()
    _initialised = True


def _init_logging() -> None:
    """Install the JSON formatter if requested. Idempotent."""
    if LOG_FORMAT != "json":
        return
    root = logging.getLogger()
    for h in root.handlers:
        if getattr(h, "_roastgpt_json", False):
            return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler._roastgpt_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    log.info("monitoring: JSON logging enabled")


def capture_exception(e: BaseException, **extra) -> None:
    """Best-effort Sentry capture that no-ops if Sentry is off."""
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_exception(e)
    except Exception:
        pass


def capture_message(msg: str, level: str = "info", **extra) -> None:
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(msg, level=level)
    except Exception:
        pass
