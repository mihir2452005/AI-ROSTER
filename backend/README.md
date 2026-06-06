# RoastGPT Backend

> FastAPI 0.115 service that powers the RoastGPT chat, billing, admin, and
> Round-9 surface (contact form, notifications, system health, maintenance
> mode). Uses SQLAlchemy 2.0 typed mappers, Redis (with in-memory fallback),
> Celery-compatible task queue (with in-memory fallback), and Sentry.

## Quick start

```bash
# From this directory
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Minimum env (set in .env, or exported)
export JWT_SECRET_KEY="<32+ byte random string>"
export DATABASE_URL="postgresql://user:pass@host/db"  # or omit to fall back to local SQLite
export REDIS_URL=""                                   # leave blank to use in-memory cache
export SENTRY_DSN=""                                  # leave blank to disable Sentry
export ENVIRONMENT=development

# Run dev server
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the interactive OpenAPI explorer.

The 1-line health check: `curl http://localhost:8000/api/health` → `{"ok": true, ...}`.

## Layout

```
backend/
├── main.py                  # FastAPI app + lifespan: sentry → cache → queue → DB
├── requirements.txt
├── runtime.txt              # Python 3.12.7
├── Procfile                 # gunicorn fallback for production
├── app/
│   ├── routes.py            # /api/session/* (start, roast, end, recover, share)
│   ├── auth.py              # JWT (HS256/384/512) + bcrypt + RBAC helpers
│   ├── auth_routes.py       # /api/auth/* (register, login, refresh, me, change-password, ...)
│   ├── auth_schemas.py      # Pydantic v2 request/response models
│   ├── admin_routes.py      # /api/admin/* (RBAC-gated)
│   ├── history_routes.py    # /api/history + /api/history/sessions
│   ├── payment_routes.py    # /api/payments/* (Razorpay + webhook + 3 default plans)
│   ├── leaderboard_routes.py
│   ├── round9_routes.py     # /api/contact · /api/notifications · /api/auth/me/activity · /api/system/*
│   ├── db_models.py         # 15 tables · Role enum · PERMISSIONS catalog · Notification · ContactMessage
│   ├── cache.py             # Redis with in-memory fallback
│   ├── queue.py             # Celery-style task queue with in-memory fallback
│   ├── monitoring.py        # Sentry init + structured JSON logging + sentry_enabled()
│   ├── jobs.py              # 3 background jobs (snapshot, retention, cleanup)
│   ├── models.py            # Pydantic response models (legacy)
│   ├── utils.py             # feature flags + sanitize_text + audit log + 4 email templates
│   ├── security.py          # input validation, header extraction
│   └── filler.py            # 6 placeholder types
├── scripts/
│   ├── bootstrap_admin.py
│   ├── backup_db.py
│   ├── restore_db.py
│   └── list_db.py
└── tests/                   # 427 tests / 22 skipped
    ├── conftest.py          # shared fixtures (in-memory SQLite, rate-limit overrides)
    ├── test_audit5_fixes.py
    ├── test_audit6_features.py
    ├── test_bug_audit_*.py
    ├── test_round9_features.py     # contact, notifications, system, maintenance
    └── ...
```

## API surface (Round 9)

### Auth
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Create account, return access + refresh tokens |
| POST | `/api/v1/auth/login` | Email + password → tokens |
| POST | `/api/v1/auth/refresh` | Rotate access token |
| POST | `/api/v1/auth/logout` | Revoke the current token |
| POST | `/api/v1/auth/logout-all` | Revoke every token (bumps `token_version`) |
| POST | `/api/v1/auth/change-password` | Change password, invalidate other sessions |
| POST | `/api/v1/auth/forgot-password` | Send a reset email (always 200) |
| POST | `/api/v1/auth/reset-password` | Consume reset token, set new password |
| GET  | `/api/v1/auth/me` | Current user profile |
| PATCH| `/api/v1/auth/me` | Update full_name, gender_preference, favorite_mode |
| GET  | `/api/v1/auth/me/activity` | Recent Activity feed from the audit log |

### Chat
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/chat/session/start` | Start a new roast session |
| POST | `/api/v1/chat/session/{id}/roast` | Send a message, get the next roast |
| POST | `/api/v1/chat/session/{id}/end` | End the session, compute final score |
| POST | `/api/v1/chat/session/{id}/recover` | Resume a previous chat from history |
| POST | `/api/v1/chat/session/{id}/share` | Create a public share link |

### History
| Method | Path | Purpose |
| --- | --- | --- |
| GET    | `/api/v1/history` | Paginated message list, supports `?q=` search |
| DELETE | `/api/v1/history` | Bulk delete |
| GET    | `/api/v1/history/export?format=txt\|md\|json` | Download the full history |

### Payments (Razorpay)
| Method | Path | Purpose |
| --- | --- | --- |
| GET  | `/api/v1/payments/plans` | Public plan catalog |
| POST | `/api/v1/payments/create-order` | Create a Razorpay order |
| POST | `/api/v1/payments/verify` | Verify a captured payment, activate subscription |
| POST | `/api/v1/payments/webhook` | Razorpay webhook (HMAC-SHA256 verified) |
| GET  | `/api/v1/payments/history` | The user's payment history |

### Subscriptions
| Method | Path | Purpose |
| --- | --- | --- |
| GET  | `/api/v1/subscriptions/current` | The current subscription, if any |
| POST | `/api/v1/subscriptions/cancel` | Schedule cancellation at period end |
| POST | `/api/v1/subscriptions/upgrade` | Upgrade to a higher plan |
| POST | `/api/v1/subscriptions/downgrade` | Downgrade at period end |

### Leaderboard
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/leaderboard?period=week\|month` | Public leaderboard |

### Round 9 — contact, notifications, activity
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/contact` | Public contact form (XSS-stripped) |
| GET  | `/api/v1/admin/contact-messages` | Admin inbox, paginated, filterable by status |
| PATCH| `/api/v1/admin/contact-messages/{id}?status=` | Mark handled/spam (admin) |
| GET  | `/api/v1/notifications` | The current user's notifications |
| POST | `/api/v1/notifications/mark-read` | Mark specific ids read (scoped to caller) |
| POST | `/api/v1/notifications/mark-all-read` | Mark every notification read |
| POST | `/api/v1/admin/notifications/broadcast` | Send to all users or one (admin) |

### Round 9 — public system health
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/system/status` | DB / cache / queue / sentry / version / maintenance |
| GET | `/api/v1/system/metrics` | Prometheus text exposition (14 gauges) |
| GET | `/api/metrics` | Back-compat alias for the same Prometheus output |

### Admin
| Method | Path | Purpose |
| --- | --- | --- |
| GET   | `/api/v1/admin/stats` | Aggregate stats |
| GET   | `/api/v1/admin/users` | List users (search + pagination) |
| POST  | `/api/v1/admin/users/{id}/ban` | Ban a user |
| POST  | `/api/v1/admin/users/{id}/unban` | Unban a user |
| POST  | `/api/v1/admin/grant-subscription` | Manually grant a paid plan |
| GET   | `/api/v1/admin/feature-flags` | Read all flags |
| PATCH | `/api/v1/admin/feature-flags` | Toggle a flag |
| GET   | `/api/v1/admin/audit-logs` | Append-only audit log |
| GET   | `/api/v1/admin/charts/signups?days=30` | Daily signup counts |
| GET   | `/api/v1/admin/charts/chats?days=30` | Daily chat-message counts |

## Versioning

Every endpoint above is mounted at both `/api/v1/*` and the unversioned
`/api/*` (back-compat). A middleware strips the `/v1` segment so the same
handler serves both paths — zero code duplication.

## Rate limits

Defaults (override in your env):

| Endpoint | Limit | Window |
| --- | --- | --- |
| All routes (general) | 120 | 1 min / IP |
| `POST /auth/register` | 20 | 1 hour / IP |
| `POST /auth/login` | 30 | 1 hour / IP |
| `POST /auth/refresh` | 60 | 1 min / user |
| `POST /auth/change-password` | 10 | 1 hour / user |
| `POST /auth/forgot-password` | 5 | 1 hour / IP |
| `POST /auth/send-verification` | 5 | 1 hour / user |
| `POST /contact` | 10 | 1 hour / IP |
| Admin cleanup | 10 | 1 hour / admin |

Every response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`. Exceeding a limit returns **429** with `Retry-After`.

## RBAC

Six roles, ascending privilege: `user` → `moderator` → `support` → `finance`
→ `admin` → `super_admin`. 14 named permissions drive the matrix — see
`app/auth.py` for the catalog and the `require_role` / `require_permission`
dependencies.

## Maintenance mode

Toggle the `maintenance_mode` feature flag from the admin UI (or via
`PATCH /api/v1/admin/feature-flags`):

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/feature-flags \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"key": "maintenance_mode", "enabled": true}'
```

When on, the `maintenance_middleware` returns **503** to every non-admin
caller for any `/api/*` path. The skip list keeps monitoring alive:
`/api/health`, `/api/v1/system/status`, `/api/v1/system/metrics`,
`/api/metrics`. The middleware also does a fresh DB read on every request
(no 60s cache) so an admin's toggle takes effect immediately.

## Email templates (dev-mode friendly)

`utils.py` ships four plain-text templates — all best-effort, all log-only
in dev (no `SMTP_HOST`):

- `send_welcome_email(to, name)` — sent on register
- `send_payment_success_email(to, plan_name, period_end_iso)` — sent on payment verify
- `send_subscription_expiring_email(to, plan_name, days_left)` — sent 3 days before period end
- `send_subscription_cancelled_email(to, plan_name)` — sent on cancel

Wrap your own call site in `try/except` if you need a non-best-effort
guarantee.

## Tests

```bash
pytest                 # full suite
pytest -q              # quieter
pytest tests/test_round9_features.py  # just Round 9
```

The fixture in `tests/conftest.py` builds a fresh in-memory SQLite schema
per test and provides wide-open rate-limit overrides so the suite runs
in ~2 min without flakiness. **427 tests / 22 skipped** as of Round 9.

## Observability

- Sentry — `sentry-sdk` initialised in the lifespan, gated on `SENTRY_DSN`.
  `sentry_enabled()` is exposed for the `/system/status` probe.
- JSON logging — every request goes through a structured logger so
  Render's log drain is greppable.
- Prometheus — `/api/v1/system/metrics` serves a `text/plain; version=0.0.4`
  document with 14 gauges: build info, uptime, users total, active subs,
  chat messages, payments, cache backend, queue backend, DB / cache /
  queue / Sentry up, maintenance mode.
- Audit log — `app.db_models.AuditLog` records every sensitive action.
  The Account page reads the user's own rows via
  `GET /api/v1/auth/me/activity`; admins get the full picture via
  `GET /api/v1/admin/audit-logs`.

## Deployment

See [`../DEPLOY.md`](../DEPLOY.md) for the full step-by-step Render + Vercel
+ Upstash + Sentry walkthrough. The short version: push to `main`, let
Render pick up the web service + cron, point the frontend at the backend
URL, set the env vars, and you're done.
