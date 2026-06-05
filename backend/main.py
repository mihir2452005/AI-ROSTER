"""FastAPI app entry point for the RoastGPT engine."""
from __future__ import annotations

import logging
import os
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Dict

from dotenv import load_dotenv

# Load .env file (if present) so DATABASE_URL and Razorpay keys are available.
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Allow running directly: `python main.py` or via `uvicorn main:app`
try:
    from app.config import LIBRARY_PATH
    from app.library import LIB
    from app.routes import router
    from app.auth_routes import router as auth_router
    from app.payment_routes import router as payments_router, sub_router
    from app.admin_routes import router as admin_users_router
    from app.history_routes import router as history_router
    from app.leaderboard_routes import router as leaderboard_router
    from app.database import init_db, get_db
    from app import auth as auth_module
    from app import payment_routes  # to seed plans on startup
except ImportError:
    from backend.app.config import LIBRARY_PATH  # type: ignore
    from backend.app.library import LIB          # type: ignore
    from backend.app.routes import router        # type: ignore
    from backend.app.auth_routes import router as auth_router  # type: ignore
    from backend.app.payment_routes import router as payments_router, sub_router  # type: ignore
    from backend.app.admin_routes import router as admin_users_router  # type: ignore
    from backend.app.history_routes import router as history_router  # type: ignore
    from backend.app.leaderboard_routes import router as leaderboard_router  # type: ignore
    from backend.app.database import init_db, get_db  # type: ignore
    from backend.app import auth as auth_module  # type: ignore
    from backend.app import payment_routes  # type: ignore  # to seed plans on startup

# CORS — configurable via env var. In dev, allow localhost:3000.
# In production, set ALLOWED_ORIGINS to your frontend domain(s).
#
# We parse the env var carefully: a stray space (`"a.com, b.com"`)
# used to produce origins with leading spaces, which never matched
# CORS preflights — silently disabling CORS in dev. An empty string
# produced `[""]` which matched nothing. The list comprehension
# below strips whitespace and drops empties.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("roastgpt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to start in production with dev defaults. See backend/app/auth.py.
    auth_module.validate_secrets(
        allow_insecure=os.environ.get("ALLOW_INSECURE_DEFAULTS", "").lower() in ("1", "true"),
    )

    log.info("loading roast library from %s", LIBRARY_PATH)
    LIB.load(LIBRARY_PATH)
    log.info(
        "ready: %d roasts across %d modes, %d personalities, %d intents",
        sum(len(p) for p in LIB.roasts_by_mode.values()),
        len(LIB.roasts_by_mode),
        len(LIB.personalities),
        len(LIB.intents),
    )

    # Initialise the database (creates tables on first run).
    log.info("initialising database...")
    try:
        init_db()
        # Seed default subscription plans (idempotent).
        from sqlalchemy.orm import Session
        with next(get_db()) as db:  # type: Session
            payment_routes.seed_plans(db)
            # Seed the achievement catalog (idempotent).
            from app import utils as app_utils
            app_utils.seed_achievements(db)
        log.info("database ready")
    except Exception as e:
        log.error("database init failed (continuing without DB): %s", e)

    # Start the in-process background jobs (leaderboard snapshot,
    # retention sweep). On the free tier these run inside the web
    # process; on a worker dyno, swap to APScheduler/celery.
    from app import jobs
    jobs.start_scheduler()

    yield

    # Shutdown
    jobs.stop_scheduler()


app = FastAPI(
    title="RoastGPT",
    version="0.1.0",
    description="The internet's most ruthless AI roaster.",
    lifespan=lifespan,
)

# CORS — open in dev; lock down in production to your frontend domain.
# We restrict methods and headers to a known allow-list rather than
# `["*"]` to reduce the CORS attack surface (a future
# `ALLOWED_ORIGINS=*` config would otherwise pair a wildcard origin
# with credentials, which is the canonical CORS misconfiguration).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

# Body size cap: reject any request over MAX_BODY_BYTES (default 5MB) with
# 413 Payload Too Large. Starlette/Uvicorn will buffer the entire body
# before passing it to the route, so without this an attacker can DoS the
# server with a single large upload. Capped server-side at 50 MB so a
# misconfigured MAX_BODY_BYTES env var can't disable the cap entirely.
MAX_BODY_BYTES = min(int(os.environ.get("MAX_BODY_BYTES", str(5 * 1024 * 1024))), 50 * 1024 * 1024)


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    """Reject oversized request bodies.

    Two checks:
    1. `Content-Length` header — easy to spoof, but cheap to check.
    2. `Transfer-Encoding: chunked` — a client can stream an
       arbitrarily-large body with no Content-Length. We refuse the
       request up-front rather than buffering the body and then
       rejecting it (which would still allocate the memory). For our
       API, no legitimate client should be using chunked transfer
       encoding.
    """
    from fastapi.responses import JSONResponse
    cl = request.headers.get("content-length")
    te = request.headers.get("transfer-encoding", "").lower()
    if "chunked" in te and cl is None:
        return JSONResponse(
            status_code=411,
            content={"detail": "Chunked transfer encoding is not allowed; send Content-Length."},
        )
    if cl is not None:
        try:
            if int(cl) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large (>{MAX_BODY_BYTES} bytes)"},
                )
        except ValueError:
            pass  # malformed Content-Length — let downstream handle it
    return await call_next(request)

# Security headers middleware. Applied to ALL responses, including
# ones built by other middleware (413/429) and the JSONResponse that
# FastAPI builds for uncaught exceptions. (Previously the
# `await call_next(...)` would propagate the error, and a 500 would
# reach the client without these headers — clickjacking surface.)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        # The global exception handler (or Starlette's default) will
        # produce the final response. Re-raise to let the normal
        # flow build it; security headers are applied to whatever
        # the next middleware in the chain emits.
        raise
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # NOTE: X-XSS-Protection was removed. Modern browsers ignore it;
    # old browsers used it as a signal to disable their (vulnerable)
    # XSS auditor. Sending it is a net negative.
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # HSTS — only useful behind TLS termination. Uncomment in
    # production where HTTPS is enforced at the edge.
    # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Rate limiting: requests per minute per IP
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))  # seconds

# Stricter per-endpoint overrides. Sensitive endpoints (register, login,
# refresh, password reset) get a tighter cap to slow down brute-force
# and account-enumeration attacks. See audit #4 + #15.
# Format: path prefix -> (max_requests, window_seconds)
RATE_LIMIT_OVERRIDES: Dict[str, tuple] = {
    "/api/auth/register": (int(os.environ.get("RATE_LIMIT_REGISTER", "5")), 60),
    "/api/auth/login": (int(os.environ.get("RATE_LIMIT_LOGIN", "10")), 60),
    "/api/auth/refresh": (int(os.environ.get("RATE_LIMIT_REFRESH", "20")), 60),
    "/api/session/start": (int(os.environ.get("RATE_LIMIT_SESSION_START", "10")), 60),
    # /api/auth/me and /api/auth/change-password are behind JWT auth
    # so they're naturally rate-limited per logged-in user. A
    # misbehaving client can still hammer them — cap at 60/min to
    # match the global default.
    "/api/auth/me": (60, 60),
    # The admin cleanup endpoint uses X-Admin-Key auth (not JWT), so
    # it's not covered by the auth-* overrides. Cap it tightly because
    # the only legitimate caller is a cron job.
    "/api/admin/cleanup": (int(os.environ.get("RATE_LIMIT_ADMIN_CLEANUP", "5")), 60),
    # Webhooks get their own bucket so a Razorpay delivery storm
    # doesn't trip our per-IP rate limit and cause Razorpay to
    # retry-with-backoff (which would amplify the storm).
    "/api/payments/webhook": (int(os.environ.get("RATE_LIMIT_WEBHOOK", "120")), 60),
    # /api/auth/change-password is per-user (JWT) but a stolen token
    # can still attempt many old-password guesses. Cap to slow down
    # dictionary attacks on the current_password field.
    "/api/auth/change-password": (int(os.environ.get("RATE_LIMIT_CHANGE_PW", "5")), 60),
    # /api/admin/grant-subscription and update_user are admin-only
    # but a compromised admin should be slowed down. Cap to 30/min
    # (one action every 2s) — enough for legitimate bulk operations.
    "/api/admin/grant-subscription": (30, 60),
    "/api/admin/users": (60, 60),
}
# Trusted reverse proxies (CIDR list, comma-separated). When a request
# arrives from one of these, we honour the X-Forwarded-For header; for
# any other source we ignore X-Forwarded-For and use request.client.host
# directly. Without this, an attacker can rotate X-Forwarded-For to give
# themselves a fresh rate-limit bucket on every request. See C4 in the
# audit. In dev (no TRUSTED_PROXIES set) we still honour the header
# because localhost is implicitly trusted.
_TRUSTED_PROXIES_RAW = os.environ.get("TRUSTED_PROXIES", "127.0.0.1/32,::1/128")
TRUSTED_PROXY_CIDRS = [
    c.strip() for c in _TRUSTED_PROXIES_RAW.split(",") if c.strip()
]


def _is_trusted_proxy(ip: str) -> bool:
    import ipaddress
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in TRUSTED_PROXY_CIDRS:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _extract_client_ip(request: Request) -> str:
    """Return the most likely real client IP.

    If the direct connection is from a trusted proxy, walk the
    X-Forwarded-For chain RIGHT-to-LEFT and return the first entry
    that is NOT a trusted proxy. This handles the common
    "client → untrusted-proxy → trusted-proxy → app" case correctly:
    the leftmost entry is the spoofable client-supplied value, the
    rightmost is appended by the trusted proxy and is the real
    client. (The previous implementation read the leftmost, which is
    the standard rule ONLY when the trusted proxy replaces — not
    appends to — the X-Forwarded-For header. See C4 / BUG-MAIN-006.)

    If the direct connection is NOT from a trusted proxy, we use
    request.client.host directly and ignore X-Forwarded-For. Without
    this, an attacker could rotate X-Forwarded-For to give themselves
    a fresh rate-limit bucket on every request.
    """
    direct = request.client.host if request.client else ""
    if not _is_trusted_proxy(direct):
        return direct or "unknown"
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        # Walk right-to-left, return the first IP that is not in
        # TRUSTED_PROXY_CIDRS. The leftmost entry is the spoofable
        # client-supplied value, so we don't trust it directly.
        for entry in reversed([e.strip() for e in fwd.split(",")]):
            if entry and not _is_trusted_proxy(entry):
                return entry
        # All entries were trusted proxies (unusual). Fall through.
    real = request.headers.get("X-Real-IP")
    if real and not _is_trusted_proxy(real.strip()):
        return real.strip()
    return direct or "unknown"
# Cap on the number of distinct IPs we track. After this we evict the
# least-recently-active entry. Prevents an attacker from filling memory
# by hitting the API from many random IPs.
RATE_LIMIT_TRACKED_IPS = int(os.environ.get("RATE_LIMIT_TRACKED_IPS", "10000"))
_request_history: Dict[str, list] = defaultdict(list)
_last_seen: Dict[str, float] = {}


def _evict_one_if_full() -> None:
    if len(_request_history) <= RATE_LIMIT_TRACKED_IPS:
        return
    # Evict the IP with the oldest last-seen timestamp.
    victim = min(_last_seen, key=_last_seen.get)  # type: ignore[arg-type]
    _request_history.pop(victim, None)
    _last_seen.pop(victim, None)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        # Skip rate limiting for health check so monitors can poll freely.
        if request.url.path == "/api/health":
            return await call_next(request)

        # Extract client IP, honouring X-Forwarded-For only when the
        # direct connection is from a trusted proxy. See _extract_client_ip
        # for the trust model.
        ip = _extract_client_ip(request)

        # Per-endpoint overrides get a tighter cap. Sensitive endpoints
        # (register, login, etc.) are matched on path prefix.
        limit = RATE_LIMIT_REQUESTS
        window = RATE_LIMIT_WINDOW
        for prefix, (l, w) in RATE_LIMIT_OVERRIDES.items():
            if request.url.path == prefix or request.url.path.startswith(prefix + "/"):
                limit = l
                window = w
                break

        now = time.time()
        window_start = now - window

        # Bound the per-IP request list. Even under sustained abuse the
        # list will never exceed the limit (the cap below).
        request_history = _request_history[ip]
        while request_history and request_history[0] < window_start:
            request_history.pop(0)
        # Hard cap: if the IP is sending requests faster than we can age
        # them out, drop the oldest to keep memory bounded.
        while len(request_history) >= limit:
            request_history.pop(0)

        # Check limit
        if len(request_history) >= limit:
            # Return a JSONResponse directly rather than raising
            # HTTPException. The exception would be re-raised by
            # Starlette's middleware handler and the response would
            # not include the security headers from
            # `add_security_headers` (which is registered LATER and
            # therefore outer in the ASGI chain). Building the
            # response here means we control every header.
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Max {limit} requests per {window}s. "
                              f"Try again later."
                },
                headers={"Retry-After": str(window)},
            )

        # Add current request
        request_history.append(now)
        _last_seen[ip] = now
        _evict_one_if_full()

    response = await call_next(request)
    return response

# Mount all routers. Order matters only when paths collide - they don't here.
app.include_router(router)                         # core roast engine
app.include_router(auth_router)                    # /api/auth/*
app.include_router(payments_router)                # /api/payments/*
app.include_router(sub_router)                     # /api/subscriptions/*
app.include_router(history_router)                 # /api/history/*
app.include_router(leaderboard_router)             # /api/leaderboard/* (public)
app.include_router(admin_users_router)             # /api/admin/* (admin user mgmt)
# Note: backend/app/routes.py also has /api/admin/cleanup (session cleanup).
# That route stays under the original router (legacy admin endpoint).
# We intentionally split: admin_users_router is the new user/admin management UI.


@app.get("/")
def root() -> dict:
    return {
        "name": "RoastGPT",
        "version": app.version,
        "docs": "/docs",
        "health": "/api/health",
    }
