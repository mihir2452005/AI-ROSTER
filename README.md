# RoastGPT 🔥

> The internet's most ruthless AI roaster. Built as a degree project, evolved into a production-ready SaaS.

Chat with an AI whose only mission is to roast you. Pick a mode, pick a personality, get destroyed. Sign up, subscribe, and climb the leaderboard.

---

## What's in the box

```
AI ROSTER/
├── DEPLOY.md                   # step-by-step deploy to Render + Vercel
├── ROAST_LIBRARY.md            # design doc for the template engine
├── render.yaml                 # Render Blueprint (backend + Postgres)
├── vercel.json                 # Vercel config (frontend)
├── .env.example                # all env vars documented
│
├── roast-library/              # 187 pre-written roasts + 20 special templates
│   ├── schema.json             # (now supports "roaster" placeholder type)
│   ├── openers.json (9)        # (2 new personalized)
│   ├── closers.json (6)        # (1 new personalized)
│   └── roasts/
│       ├── general.json    (10)  friendly.json  (22)
│       ├── savage.json     (28)  programmer.json (27)  ← +4 personalized
│       ├── student.json    (26)  gamer.json      (24)
│       ├── corporate.json  (24)  startup.json    (26)
│
├── backend/                    # FastAPI engine + auth + payments + admin
│   ├── main.py
│   ├── runtime.txt             # 3.12.7 for Render
│   ├── Procfile                # gunicorn fallback
│   ├── requirements.txt        # fastapi, sqlalchemy, jose, passlib, razorpay
│   ├── scripts/
│   │   └── bootstrap_admin.py  # one-shot admin creation
│   ├── app/                    # engine + auth + payments + history
│   │   ├── routes.py           # /api/session/* (now with chat-history persistence)
│   │   ├── auth.py             # JWT + bcrypt + dependencies
│   │   ├── auth_routes.py      # /api/auth/{register,login,refresh,me,...}
│   │   ├── payment_routes.py   # /api/payments/* + 3 default plans
│   │   ├── admin_routes.py     # /api/admin/* (users, leaderboard, grant)
│   │   ├── history_routes.py   # /api/history
│   │   ├── leaderboard_routes.py # /api/leaderboard (public, masked)
│   │   ├── db_models.py        # User, Subscription, Payment, ChatHistory...
│   │   ├── filler.py           # 6 placeholder types (added "roaster")
│   │   └── ...
│   └── tests/                  # 302 tests passing in ~30s
│
└── frontend/                   # Next.js 14 chat UI
    ├── app/
    │   ├── page.tsx            # landing + start session (with personalized roasts)
    │   ├── chat/[sessionId]/   # chat client
    │   ├── login/              # sign in
    │   ├── register/           # sign up
    │   ├── pricing/            # 3 plans + Razorpay checkout
    │   ├── account/            # profile + subscription + payments
    │   ├── history/            # past roasts (authenticated users)
    │   ├── admin/              # user mgmt + leaderboard + grant
    │   └── leaderboard/        # public weekly/monthly/all-time board
    ├── components/
    │   ├── HeaderAuth.tsx      # nav links react to login state
    │   └── ScorePanel.tsx
    └── lib/
        ├── api.ts              # auto-injects bearer token, maps 402 → free_tier
        ├── auth-api.ts         # /api/auth, /api/payments, /api/admin
        └── types.ts
```

## Quick start (development)

### 1. Start the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env         # edit values
uvicorn main:app --reload --port 8000
```

The API is at `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

### 2. Start the frontend (in a new terminal)

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

The UI is at `http://localhost:3000`.

### 3. Bootstrap an admin (optional, for testing the admin dashboard)

```bash
cd backend
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=YourStrongPass123 python -m scripts.bootstrap_admin
```

### 4. Run the tests

```bash
cd backend
RATE_LIMIT_REQUESTS=10000 RATE_LIMIT_WINDOW=1 \
  ADMIN_API_KEY=dev-secret-change-in-prod \
  DATABASE_URL=sqlite:///./test.db \
  JWT_SECRET_KEY=test-secret-key-32-bytes-minimum-1234 \
  .venv\Scripts\python -m pytest tests -v
```

You should see `302 passed, 19 skipped`.

## Deploying to production

See **[DEPLOY.md](DEPLOY.md)** for a full walkthrough. The short version:

- Push this repo to GitHub.
- On Render, create a new Blueprint pointing at the repo. It picks up `render.yaml` and provisions the FastAPI service + Postgres.
- On Vercel, import the repo with root directory `frontend`. Set `NEXT_PUBLIC_API_URL` to the Render URL.
- Bootstrap your first admin via the Render Shell tab.

No Docker required anywhere.

## Architecture

```
Browser ──HTTPS──▶ Vercel (Next.js)
                       │
                       │  fetch /api/*
                       ▼
              Render (FastAPI + gunicorn)
                       │
                       ├── PostgreSQL (users, subs, history, leaderboard)
                       ├── Razorpay (payments + webhooks)
                       └── RoastEngine (pure string + dict ops, no LLM)
```

No LLM is called for the template layer. Every roast is composed from the
JSON library at `roast-library/`. The 1% of traffic that escalates is a TODO.

## Features

### For users
- 8 roast modes × 6 personalities → 48 combinations
- 3 subscription plans (Starter ₹299/10d, Pro ₹799/30d, Legend ₹1999/90d)
- Free tier: 5 messages per account, then prompted to subscribe
- Persistent chat history (view all your past roasts at `/history`)
- Public leaderboard with weekly / monthly / all-time views
- Personalized roasts: roaster pronoun/title matches the gender you picked at signup
- Account page: profile, subscription status, payment history, cancel

### For admins
- `/admin` dashboard with stats (total users, active subs, revenue)
- User list with search and inline toggle for `is_active` / `is_verified` / `is_admin`
- Grant a subscription to any user (no payment) — useful for support / promos
- Leaderboard with weekly/monthly tabs to find reward candidates

### For ops
- CORS locked to your domains via `ALLOWED_ORIGINS`
- Rate-limited (60 req/min per IP, configurable)
- Safety-filtered output (no slurs, no protected classes, no self-harm encouragement)
- Webhook-driven subscription activation (Razorpay → backend → DB)
- Best-effort chat history persistence (writes never break a request)

## Spec coverage

| Spec feature | Status |
|--------------|--------|
| AI Roast Chat | ✅ template layer (no LLM) |
| 8 Roast Modes | ✅ all 8 with 10–28 roasts each |
| 6 Personalities | ✅ all 6 with damage filters |
| Roast Score System | ✅ confidence, damage, delusion, recovery |
| Shareable Conversations | ✅ `/share/[id]` page |
| Leaderboards | ✅ real, persisted, public + admin views |
| AI Memory | ✅ session callbacks + user memory in engine |
| User accounts | ✅ email/password + JWT + bcrypt |
| Payments | ✅ Razorpay (3 plans + webhooks) |
| Subscriptions | ✅ active / cancel / admin-grant |
| Admin dashboard | ✅ stats + users + leaderboard + grant |
| Chat history | ✅ persisted per user, viewable in `/history` |
| Personalized roasts | ✅ user name + roaster gender |
| Deploy to Render + Vercel | ✅ no Docker |
| Layer 2 (9% dynamic builder) | ❌ not yet |
| Layer 3 (1% LLM escalation) | ❌ not yet |
| Voice roasting | ❌ not yet |
| Multiplayer rooms | ❌ not yet |

See `ROAST_LIBRARY.md` §12 for the long-term roadmap and §20 for details on
the user/auth/payment layer added in this phase.
