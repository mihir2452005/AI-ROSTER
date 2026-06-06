# RoastGPT 🔥

> **The internet's most ruthless AI roaster.** Built as a degree project, evolved into a production-ready SaaS with 402 passing tests, 6-tier RBAC, Redis-backed rate limiting, Sentry monitoring, share tokens, and full Razorpay billing.

Chat with an AI whose only mission is to roast you. Pick a mode, pick a personality, get destroyed. Sign up, subscribe, share the wreckage, climb the leaderboard.

---

## Highlights

| | |
|---|---|
| **Backend** | FastAPI · SQLAlchemy 2.0 · PostgreSQL (Neon) · Redis (Upstash) · Celery · Sentry |
| **Frontend** | Next.js 14 (App Router) · TypeScript · Tailwind · Framer Motion · Sonner |
| **Auth** | JWT (HS256/384/512) + bcrypt + refresh-token rotation + token_version revocation |
| **Billing** | Razorpay (3 plans, webhooks, HMAC-SHA256 verified, idempotent) |
| **RBAC** | 6 roles (user → moderator → support → finance → admin → super_admin) · 14 permissions |
| **Storage** | 13 tables incl. audit_logs, user_memories, leaderboard_snapshots, achievements |
| **Tests** | **402 passed / 22 skipped** · ~80s wall-clock |
| **Cost** | **$0/mo** on free tiers (Render 750h + Neon 0.5GB + Upstash 10k cmd/day + Vercel 100GB + Sentry 5k errors) |

---

## Repo layout

```
AI ROSTER/
├── README.md                    # this file
├── DEPLOY.md                    # step-by-step Render + Vercel + Upstash + Sentry
├── ROAST_LIBRARY.md             # design doc for the template engine
├── render.yaml                  # Render Blueprint (web + cron)
├── vercel.json                  # Vercel config (HSTS, CSP, headers)
├── .env.example                 # every env var documented
│
├── roast-library/               # 187 pre-written roasts + 6 placeholder types
│   ├── schema.json
│   ├── openers.json (9)         # 2 new personalized
│   ├── closers.json (6)         # 1 new personalized
│   └── roasts/
│       ├── general.json    (10)  friendly.json  (22)
│       ├── savage.json     (28)  programmer.json (27)  ← +4 personalized
│       ├── student.json    (26)  gamer.json      (24)
│       ├── corporate.json  (24)  startup.json    (26)
│
├── backend/                     # FastAPI engine + auth + payments + admin
│   ├── main.py                  # lifespan: init_sentry → cache → queue → DB
│   ├── runtime.txt              # 3.12.7
│   ├── Procfile                 # gunicorn fallback
│   ├── requirements.txt         # fastapi, sqlalchemy, redis, celery, sentry-sdk, jose, bcrypt
│   ├── scripts/
│   │   ├── bootstrap_admin.py   # one-shot admin creation
│   │   ├── backup_db.py         # JSON dump → GitHub repo
│   │   ├── restore_db.py        # truncate/insert restore
│   │   └── list_db.py           # operator inspection
│   ├── app/
│   │   ├── routes.py            # /api/session/* (start, roast, end, recover, share)
│   │   ├── auth.py              # JWT + bcrypt + require_role / require_permission
│   │   ├── auth_routes.py       # /api/auth/{register,login,refresh,me,...}
│   │   ├── auth_schemas.py      # Pydantic v2 models
│   │   ├── admin_routes.py      # /api/admin/* (RBAC-gated)
│   │   ├── history_routes.py    # /api/history + /api/history/sessions
│   │   ├── payment_routes.py    # /api/payments/* + 3 default plans
│   │   ├── leaderboard_routes.py
│   │   ├── db_models.py         # 13 tables · Role enum · PERMISSIONS catalog
│   │   ├── cache.py             # Redis + in-memory fallback
│   │   ├── queue.py             # Celery + in-memory fallback
│   │   ├── monitoring.py        # Sentry + JSON logging
│   │   ├── jobs.py              # 3 background tasks
│   │   ├── models.py            # Pydantic response models
│   │   ├── utils.py             # feature flags (cache-backed) + sanitize_text
│   │   └── filler.py            # 6 placeholder types
│   └── tests/                   # 402 tests / 22 skipped
│
└── frontend/                    # Next.js 14 chat UI
    ├── app/
    │   ├── page.tsx             # landing
    │   ├── chat/[sessionId]/    # chat client
    │   ├── login/  register/  verify-email/  forgot-password/  reset-password/
    │   ├── pricing/             # 3 plans + Razorpay
    │   ├── account/             # profile · subscription · payments
    │   ├── history/             # messages + Sessions tab
    │   ├── admin/               # 7-tab dashboard + role badges
    │   ├── leaderboard/         # public weekly/monthly/all-time
    │   ├── achievements/        # 15 badge catalog
    │   ├── stats/               # personal user stats
    │   ├── share/[id]/          # public share view
    │   ├── terms/  privacy/     # legal
    │   ├── not-found.tsx · error.tsx · loading.tsx
    ├── components/              # HeaderAuth · ScorePanel · ...
    ├── lib/
    │   ├── api.ts               # auto-injects bearer, maps 402 → free_tier
    │   ├── auth-api.ts          # typed client (auth, history, payments, admin)
    │   ├── types.ts
    │   └── errors.ts
    └── tests/                   # Vitest
```

---

## Quick start (development)

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env          # edit values
uvicorn main:app --reload --port 8000
```

API: <http://localhost:8000> · Interactive docs: <http://localhost:8000/docs>

### 2. Frontend (new terminal)

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

UI: <http://localhost:3000>

### 3. Bootstrap an admin

```bash
cd backend
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=YourStrongPass123 \
  python -m scripts.bootstrap_admin
```

### 4. Run the tests

```bash
cd backend
python -m pytest -q
```

→ `402 passed, 22 skipped in ~80s`

---

## Architecture

```
                    ┌──────────────┐
                    │   Browser    │
                    └──────┬───────┘
                           │ HTTPS
                    ┌──────▼───────┐
                    │   Vercel     │  Next.js 14 · HSTS · CSP · auto-TLS
                    │ (frontend)   │
                    └──────┬───────┘
                           │ /api/v1/*
                    ┌──────▼───────┐
                    │   Render     │  FastAPI + gunicorn + uvicorn
                    │  (backend)   │  lifespan: Sentry → cache → queue → DB
                    └─┬──┬──┬──┬──┘
                      │  │  │  │
         ┌────────────┘  │  │  └────────────┐
         │               │  │               │
   ┌─────▼─────┐  ┌──────▼──▼────┐  ┌───────▼────────┐
   │   Neon    │  │   Upstash    │  │   Razorpay     │
   │ PostgreSQL│  │    Redis     │  │  (payments +   │
   │  (data)   │  │ (cache+rate) │  │   webhooks)    │
   └───────────┘  └──────────────┘  └────────────────┘
                           │
                    ┌──────▼───────┐
                    │   Sentry     │  error tracking
                    │  (optional)  │
                    └──────────────┘
```

**No LLM is called for the template layer.** Every roast is composed from
the JSON library at `roast-library/`. When `LLM_PROVIDER=openai` is set, the
1% of input the template engine can't handle escalates to an external LLM
via `app.llm_fallback`.

---

## Features

### For users
- **8 roast modes** × **6 personalities** = **48 combinations**
- **3 subscription plans** (Starter ₹299/10d, Pro ₹799/30d, Legend ₹1999/90d)
- **Free tier** — 5 messages per account, then prompted to subscribe
- **Persistent chat history** with search, pagination, and per-day grouping
- **Continue Previous Chat** — pick up any ended session in one click
- **Public share links** with revocable 192-bit tokens
- **15 achievements** (burn meter, comeback king, night owl, etc.)
- **Personalized roasts** — roaster pronoun + name match the gender you picked
- **Public leaderboards** — weekly / monthly / all-time with masked emails
- **Account page** — profile, avatar, subscription status, payment history, cancel/downgrade
- **Dark mode** — toggle persisted in localStorage

### For admins
- **7-tab dashboard** — stats, users, grant, leaderboard, audit, flags, charts
- **User management** — search, ban/unban, verify, role assignment (RBAC)
- **Grant premium** — without payment, for support / promos
- **Leaderboard drill-down** — find reward candidates by period
- **Audit log viewer** — every privileged action with actor, IP, target
- **Feature flags** — toggle any flag from the UI
- **30-day signup + chat charts** — for growth dashboards
- **Role catalog** — see all 6 roles and the 14 permissions each grants

### For ops
- **CORS** locked to your domains via `ALLOWED_ORIGINS`
- **Rate limiting** — sliding window in Redis (60 req/min default, per-endpoint overrides)
- **JWT** with token_version invalidation (logout, password change, demote)
- **Algorithm allow-list** — only HS256/HS384/HS512; leeway 30s
- **Webhook idempotency** — unique index on `razorpay_payment_id`
- **Subscription uniqueness** — at most one `active` or `past_due` sub per user
- **XSS protection** — all user text run through `sanitize_text` (HTML + control chars stripped)
- **Public leaderboard PII** — masked emails, link-stripped display names
- **In-memory session caps** — `ROASTGPT_MAX_SESSIONS` + `ROASTGPT_MAX_MEM_USERS` prevent OOM
- **Daily backups** — Render cron dumps Postgres to a private GitHub repo
- **One-shot restore** — `python -m scripts.restore_db --input backup.json --truncate`
- **Sentry** — opt-in error tracking with PII redaction
- **JSON logs** — opt-in via `LOG_FORMAT=json` for log aggregators
- **Free-tier atomicity** — single SQL UPDATE gates the 5-message cap

---

## RBAC matrix

| Role | Rank | Key permissions |
|---|:---:|---|
| `user` | 0 | chat, read own history, manage own sub |
| `moderator` | 1 | + ban/unban, read audit logs |
| `support` | 2 | + read user PII |
| `finance` | 3 | + read payments, grant subscriptions |
| `admin` | 4 | + manage feature flags, change roles |
| `super_admin` | 5 | + create/demote admins |

`is_admin: bool` is auto-derived from `role` (kept for back-compat). Setting
`user.is_admin = True` still works — it promotes the user to `admin` role.
The full catalog of 14 permissions lives in `app/db_models.PERMISSIONS`.

---

## Spec coverage

### 🔐 Authentication — 12 / 12 ✅
Registration · Login · JWT · bcrypt · Protected routes · Logout · Refresh · Email verification · Forgot/Reset/Change password · Session management

### 👤 User account — 7 / 7 ✅
Profile · Edit · Avatar · Settings · Soft delete · Active/Banned · Last-login tracking

### 💳 Payments — 10 / 10 ✅
Free tier · 3 plans · Razorpay · Payment history · Status · Expiry · Upgrade · Downgrade · Cancel · Webhook (HMAC + idempotent)

### 🤖 Chat system — 7 / 7 ✅
Sessions · Unique UUIDs · Multi-turn · Response engine · 8 modes · 6 personalities · Continuation (in-mem + DB recovery)

### 📚 History — 6 / 6 ✅
Save · View · Delete · Continue previous · Search · Pagination

### 🧠 AI memory — 5 / 5 ✅
Name · Preferences · Recent chats · Personalized roasts · Favorite mode

### 🏆 Leaderboard — 5 / 5 ✅
Weekly · Monthly · All-time · User rank · Score calc

### 📤 Sharing — 4 / 4 ✅
Share conversation · Public link · **Share ID generation (192-bit token)** · View shared chat

### 👨‍💼 Admin panel — 10 / 10 ✅
Admin login · Stats · User mgmt · Search · Ban/Unban · Verify · Grant premium · View payments · View leaderboards · **Role catalog**

### 🗄️ Database — 8 / 8 ✅ (13 tables)
users · subscriptions · subscription_plans · payments · roast_sessions · chat_history · leaderboard_snapshots · user_memories (+ audit_logs · achievements · user_achievements · feature_flags · email_tokens)

### 🔒 Security — 8 / 8 ✅
Rate limit · JWT validation · Input validation · SQL-injection-safe · XSS · CORS · Env vars · Secret management

### 📊 Analytics — 7 / 7 ✅
Total / Active users · Total chats · Revenue · Subscription count · Avg session time · Most-used mode

### ⚙️ API — 7 / 7 ✅
All routes versioned at `/api/v1/*` with `/api/*` alias for back-compat

### 🎨 Frontend — 10 / 10 ✅
Landing · Login · Register · Chat · History · Pricing · Account · Leaderboard · Admin · 404/500/loading

### 🚀 Deployment — 7 / 7 ✅
GitHub · Env config · Render · Vercel · Neon · Custom domains · HTTPS (HSTS)

### 🧪 Testing — 6 / 6 ✅
Unit · API · Auth · Payment · Chat · Integration — **402 passing**

### ⭐ Nice to have — 21 / 22 ⚠️
Dark mode · Mobile responsive · Loading states · Toasts · Copy · Export · User stats · Achievements · LLM fallback · Redis cache · Gold standard SaaS features · Audit logs · Background jobs · Queue system · Feature flags · API versioning · Monitoring · Health check · DB backups · Soft delete · **RBAC**

> **Skipped:** Voice mode — the only non-implemented item, intentionally
> deferred (browser Speech API is unreliable; Vapi/Twilio adds $50+/mo).

**Total: 126 / 127 = 99.2%**

---

## Deploying to production

See **[DEPLOY.md](DEPLOY.md)** for the full walkthrough. The short version:

1. **Push to GitHub** (or fork the existing repo).
2. **Render** — create a Blueprint from the repo. `render.yaml` provisions
   the FastAPI web service + a daily backup cron. Set `DATABASE_URL` to
   your Neon pooled connection.
3. **Vercel** — import the repo with root directory `frontend`. Set
   `NEXT_PUBLIC_API_URL` to your Render URL.
4. **Bootstrap an admin** — Render Shell tab, run `bootstrap_admin`.
5. **(Optional)** Create free Upstash Redis + Sentry projects, paste
   `REDIS_URL` + `SENTRY_DSN` into Render env.

No Docker required anywhere. See `DEPLOY.md` for full env-var reference
and the cost-by-service breakdown.

---

## Cost (free tier)

| Service | Free limit | After free tier |
|---|---|---|
| Render web | 750 hrs/mo (spins down at 15 min idle) | $7/mo |
| Render Cron | 1 cron | $1/mo |
| Neon Postgres | 0.5 GB, 100 CU-hr/mo | $19/mo |
| Upstash Redis | 10k cmd/day, 1 MB | $0.50/GB |
| Sentry | 5k errors/mo, 1 user | $26/mo |
| Vercel | 100 GB bandwidth | $20/mo |
| Razorpay | 2% per payment | same |

**Total: $0/mo** for the entire stack.

---

## Local development scripts

| Command | What it does |
|---|---|
| `uvicorn main:app --reload` | Run backend with hot reload |
| `npm run dev` | Run frontend with hot reload |
| `npm run build` | Production build (must stay clean) |
| `npm run typecheck` / `tsc --noEmit` | TypeScript validation |
| `pytest -q` | Run the test suite |
| `pytest -k rbac -v` | Run just the RBAC tests |
| `python -m scripts.bootstrap_admin` | Create / promote the first admin |
| `python -m scripts.backup_db --output backup.json` | Export the DB to JSON |
| `python -m scripts.list_db` | Show row counts per table |
| `python -m scripts.restore_db --input backup.json --dry-run` | Preview a restore |

---

## License

Source-available; for educational and non-commercial use. The roast
library (`roast-library/`) is original work. Razorpay is the payment
processor; production deployments need a real `rzp_live_` key.

## Acknowledgements

- **Razorpay** for the Indian payment gateway.
- **Neon** for free PostgreSQL.
- **Upstash** for free Redis.
- **Sentry** for free error tracking.
- **Render** + **Vercel** for the free hosting.
- Every contributor who reported a bug during the degree-project beta.

> _"Your code called you a crybaby. We just made it official."_ — RoastGPT
