<div align="center">

<!-- HERO BANNER -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,28,40&height=220&section=header&text=RoastGPT&fontSize=80&fontColor=fff&animation=twinkling&fontAlignY=35&desc=The%20Internet%27s%20Most%20Ruthless%20AI%20Roaster&descSize=22&descColor=fff&descAlignY=55"/>

<br/>

<!-- BADGES -->
<img src="https://img.shields.io/badge/🔥_Status-Production_Ready-success?style=for-the-badge" alt="Status"/>
<img src="https://img.shields.io/badge/💰_Cost-$0%2Fmonth-brightgreen?style=for-the-badge" alt="Cost"/>
<img src="https://img.shields.io/badge/🧪_Tests-434_Passed-blue?style=for-the-badge" alt="Tests"/>
<img src="https://img.shields.io/badge/📜_License-Proprietary-red?style=for-the-badge" alt="License"/>
<img src="https://img.shields.io/badge/⚖️_Copyright-MIHIR_K_PATEL™-gold?style=for-the-badge" alt="Copyright"/>

<br/><br/>

<!-- SOCIAL -->
<a href="https://github.com/mihir2452005/AI-ROSTER/stargazers"><img src="https://img.shields.io/github/stars/mihir2452005/AI-ROSTER?style=social" alt="Stars"/></a>
<a href="https://github.com/mihir2452005/AI-ROSTER/network/members"><img src="https://img.shields.io/github/forks/mihir2452005/AI-ROSTER?style=social" alt="Forks"/></a>
<a href="https://github.com/mihir2452005/AI-ROSTER/watchers"><img src="https://img.shields.io/github/watchers/mihir2452005/AI-ROSTER?style=social" alt="Watchers"/></a>
<a href="https://github.com/mihir2452005/AI-ROSTER/issues"><img src="https://img.shields.io/github/issues/mihir2452005/AI-ROSTER?style=social" alt="Issues"/></a>

<br/><br/>

<!-- TYPING ANIMATION -->
<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=22&pause=1000&color=FF6B6B&center=true&vCenter=true&random=false&width=600&lines=Chat.+Get+Roasted.+Cry.+Repeat.;Built+with+FastAPI+%2B+Next.js;Deployed+on+100%25+Free+Tier;434+Tests+Passing+%E2%9C%93;Production+Ready+%F0%9F%9A%80" alt="Typing Animation"/>

</div>

---

<div align="center">

## ⚡ TL;DR — What is this?

**RoastGPT** is a full-stack SaaS where an AI roasts you mercilessly.
Pick a mode (savage, programmer, corporate…), pick a personality
(sarcastic friend, toxic interviewer, professor…), chat — and get
**destroyed** with a real score, a real leaderboard, and a real reason
to come back.

</div>

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   You: "I just shipped my first iOS app"                    │
│                                                              │
│   🤖 RoastGPT (Savage · Toxic Interviewer):                 │
│      "Oh, you built an iOS app? That's cute. Did your        │
│       mum test it for you, or did you bribe a friend at     │
│       Starbucks with a latte to pretend to be a user?"      │
│                                                              │
│   💀 Damage: +42                                            │
│   🏆 You moved up 3 spots on the weekly leaderboard.         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🌟 Features

<table>
<tr>
<td width="50%" valign="top">

### 🎭 8 Roast Modes
Savage, Programmer, Corporate, Student, Gamer, Startup, General, Friendly — each with its own library of 187 hand-written roasts.

### 🧠 6 Personalities
Sarcastic Friend · Toxic Interviewer · Professor · Savage One · Startup Investor · Gamer. Same mode, totally different energy.

### 🔐 Production-Grade Auth
JWT (HS256/384/512) + bcrypt + refresh-token rotation + `token_version` revocation. Change your password → every other device gets logged out instantly.

### 💳 Razorpay Billing
3 plans, HMAC-SHA256 verified webhooks, **idempotent** (no double-charges), automatic subscription activation, free-tier counter, in-app receipts.

</td>
<td width="50%" valign="top">

### 🛡️ 6-Tier RBAC
`user` → `moderator` → `support` → `finance` → `admin` → `super_admin` with **14 granular permissions**. Not a single flag — a real permission system.

### 📊 Live Leaderboard
Weekly, monthly, all-time. Hourly snapshot job so it reads in O(1) without re-aggregating the chat history.

### 🏆 15 Achievements
Welcome, first chat, 100 messages, 7-day streak, free-tier limit, subscription, share, admin actions — automatically unlocked.

### 📨 3 Notification Channels
In-app bell + email + admin broadcast. 12 templates, UTF-8, real SMTP, dev-mode log fallback.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🛡️ 3-Tier Rate Limiting
Per-IP · per-endpoint · per-user. 5 register / 10 login / 10 contact per minute. Redis-backed (survives cold starts).

### 🔍 Production Observability
`/api/v1/system/status` (db · cache · queue · sentry · version) and `/api/v1/system/metrics` in Prometheus text format.

### 🐛 Sentry Error Tracking
5K errors/month free tier. Source maps, breadcrumbs, PII scrubber, environment-tagged.

### 📤 Public Sharing
Share a session via `/share/{token}` — anyone with the link can read, no account needed. 24-hour TTL by default.

</td>
<td width="50%" valign="top">

### 📧 4 Email Templates
Welcome · Payment success · Subscription expiring · Subscription cancelled. All UTF-8, all dev-mode-logged when SMTP is unset.

### 💬 Contact Form
Public submit + admin inbox. Strips XSS, validates email, rate-limited, marks spam.

### 📜 Audit Log
Every admin action recorded with actor, IP, target, before/after diffs. Visible in `/admin`.

### 🗄️ Daily Backups
JSON dump to a private GitHub repo via the Render Cron job. Restore dry-run + truncate mode. Tested end-to-end.

</td>
</tr>
</table>

---

## 🧰 Tech Stack

<div align="center">

### Backend
<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
<img src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge" alt="SQLAlchemy"/>
<img src="https://img.shields.io/badge/PostgreSQL-15-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
<img src="https://img.shields.io/badge/Redis-Upstash-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"/>
<img src="https://img.shields.io/badge/Celery-37814A?style=for-the-badge&logo=celery&logoColor=white" alt="Celery"/>
<img src="https://img.shields.io/badge/Sentry-362D59?style=for-the-badge&logo=sentry&logoColor=white" alt="Sentry"/>
<img src="https://img.shields.io/badge/Pydantic-v2-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic"/>

### Frontend
<img src="https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js"/>
<img src="https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"/>
<img src="https://img.shields.io/badge/Tailwind-3-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind"/>
<img src="https://img.shields.io/badge/Framer_Motion-0055FF?style=for-the-badge&logo=framer&logoColor=white" alt="Framer"/>
<img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React"/>

### Infrastructure (100% Free Tier)
<img src="https://img.shields.io/badge/Render-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Render"/>
<img src="https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white" alt="Vercel"/>
<img src="https://img.shields.io/badge/Neon-00E699?style=for-the-badge&logo=neon&logoColor=white" alt="Neon"/>
<img src="https://img.shields.io/badge/Upstash-00E9A3?style=for-the-badge&logo=upstash&logoColor=white" alt="Upstash"/>
<img src="https://img.shields.io/badge/Razorpay-02042B?style=for-the-badge&logo=razorpay&logoColor=3395FF" alt="Razorpay"/>
<img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white" alt="GH Actions"/>

</div>

---

## 📊 By The Numbers

<div align="center">

| Metric | Value |
|:------:|:------|
| 🧪 **Tests Passing** | **434 passed / 22 skipped** |
| ⏱️ **Test Wall-Clock** | **~130s** |
| 📦 **Python Packages** | **27** |
| 🗃️ **Database Tables** | **13** |
| 🛣️ **API Endpoints** | **80+** |
| 🎭 **Roast Modes** | **8** |
| 🧠 **Personalities** | **6** |
| 💬 **Hand-Written Roasts** | **187** |
| 🎨 **Frontend Pages** | **24** |
| 🛡️ **RBAC Roles** | **6** |
| 🔑 **Permissions** | **14** |
| 🏆 **Achievements** | **15** |
| 📨 **Notification Templates** | **12** |
| 📧 **Email Templates** | **4** |
| 💾 **Backup Destinations** | **4** (local, http, github, s3) |
| 💰 **Monthly Cost** | **$0.00** |

</div>

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- Node 20+
- Git

### 1. Clone & enter
```bash
git clone https://github.com/mihir2452005/AI-ROSTER.git
cd AI-ROSTER
```

### 2. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env         # edit values
uvicorn main:app --reload --port 8000
```
- API → <http://localhost:8000>
- Interactive docs → <http://localhost:8000/docs>

### 3. Frontend (new terminal)
```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```
- UI → <http://localhost:3000>

### 4. Bootstrap an admin
```bash
cd backend
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=YourStrongPass123 \
  python -m scripts.bootstrap_admin
```

### 5. Run the test suite
```bash
cd backend
python -m pytest -q
# → 434 passed, 22 skipped in ~130s
```

---

## 🌐 Production Deployment (100% Free Tier)

> **Goal:** Go from `git clone` to a publicly accessible, paid-SaaS-ready, monitored, backed-up RoastGPT in **~1 hour** — at **zero cost**.

### Architecture at a Glance

```
                        ┌────────────────────┐
                        │   GitHub (repo)    │
                        └────────┬───────────┘
                                 │ git push
              ┌──────────────────┴──────────────────┐
              │                                     │
              ▼                                     ▼
     ┌────────────────┐                   ┌────────────────┐
     │  Vercel (free) │                   │ Render (free)  │
     │  Next.js SPA   │ ──HTTPS JSON──▶  │ FastAPI / Py    │
     │  CDN + edge    │                   │ gunicorn       │
     └────────────────┘                   └─┬──────────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                  │
                          ▼                  ▼                  ▼
                  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
                  │  Neon        │   │  Upstash     │   │  Sentry      │
                  │  Postgres    │   │  Redis       │   │  Errors      │
                  │  0.5 GB free │   │  10k cmd/day │   │  5k errs/mo  │
                  └──────────────┘   └──────────────┘   └──────────────┘

                  ┌────────────────────────────────────┐
                  │  Render Cron (free, 1 job)         │
                  │  → daily JSON backup to GitHub     │
                  └────────────────────────────────────┘
```

---

### Step 1 · Accounts (15 min)

Sign up for all 8 services. All free.

| # | Service | Purpose | URL |
|:-:|---------|---------|-----|
| 1 | **GitHub** | Source + backup storage | https://github.com |
| 2 | **Render** | Backend hosting | https://render.com |
| 3 | **Vercel** | Frontend hosting | https://vercel.com |
| 4 | **Neon** | PostgreSQL database | https://neon.tech |
| 5 | **Upstash** | Redis (rate limits, queues) | https://upstash.com |
| 6 | **Razorpay** | Payments (test mode for now) | https://razorpay.com |
| 7 | **Sentry** | Error monitoring | https://sentry.io |
| 8 | **Resend** | Transactional email | https://resend.com |

> **Tip:** Sign in with GitHub everywhere — saves 2 minutes per service.

---

### Step 2 · Create the Neon database (3 min)

1. Go to https://neon.tech → **New Project**.
2. Name: `roastgpt` · Region: **Oregon** (matches Render for low latency).
3. Click **Create Project**.
4. From the **Connection Details** panel, copy the **Pooled** connection string. Looks like:
   ```
   postgresql://neondb_owner:AbCdEf123@ep-cool-darkness-123456-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
5. **Save it — you'll paste it into Render in Step 4.**

> ✅ Neon free tier: 0.5 GB storage, 100 CU-hr/mo, **never expires**, never pauses.

---

### Step 3 · Get other free service credentials (10 min)

| Service | Action | Save this |
|---------|--------|-----------|
| **Upstash** | Create Redis database → region **Oregon** → copy the `REDIS_URL` | `rediss://default:xxx@xxx.upstash.io:6379` |
| **Razorpay** | Toggle to **Test mode** → Settings → API Keys → Generate Test Key → copy **Key ID** + **Key Secret** | `rzp_test_xxx` + secret |
| **Razorpay** | Settings → Webhooks → New Webhook → events: `payment.captured`, `payment.failed`, `subscription.cancelled` → copy the **Webhook Secret** | random string |
| **Sentry** | Create project (Python / FastAPI) → copy the **DSN** | `https://xxx@sentry.io/yyy` |
| **Resend** | Add & verify your domain (or use `onboarding@resend.dev` for testing) → copy **API Key** | `re_xxx` |
| **GitHub** | Settings → Developer settings → Personal access tokens → **Fine-grained** → create one scoped to a new private `roastgpt-backups` repo, permission: **Contents: Read & Write** | `github_pat_xxx` |

---

### Step 4 · Deploy the backend to Render (10 min)

1. Go to https://dashboard.render.com → **New** → **Blueprint**.
2. Connect your GitHub account & select the `AI-ROSTER` repo.
3. Render auto-detects `render.yaml` and shows two services:
   - `roastgpt-api` (web service, Python)
   - `roastgpt-backup` (cron job, runs daily at 02:13 UTC)
4. Click **Apply**. Render builds and starts the service.
5. Once the build is green, go to **`roastgpt-api` → Environment** and add:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | *(paste Neon pooled string from Step 2)* |
   | `REDIS_URL` | *(paste Upstash URL from Step 3)* |
   | `RAZORPAY_KEY_ID` | `rzp_test_xxx` |
   | `RAZORPAY_KEY_SECRET` | *(Razorpay test secret)* |
   | `RAZORPAY_WEBHOOK_SECRET` | *(Razorpay webhook secret)* |
   | `SENTRY_DSN` | *(your Sentry DSN)* |
   | `SMTP_HOST` | `smtp.resend.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USERNAME` | `resend` |
   | `SMTP_PASSWORD` | *(your Resend API key)* |
   | `SMTP_FROM` | `RoastGPT <hello@yourdomain.com>` |
   | `BACKUP_GITHUB_REPO` | `your-username/roastgpt-backups` |
   | `BACKUP_GITHUB_TOKEN` | *(your fine-grained PAT)* |
   | `ALLOWED_ORIGINS` | `https://your-app.vercel.app` *(set this AFTER Vercel deploy in Step 5)* |

6. Click **Save Changes**. Render redeploys automatically.

> ✅ `JWT_SECRET_KEY` and `ADMIN_API_KEY` are **auto-generated** by Render (`generateValue: true`).

---

### Step 4b · Bootstrap your first admin (2 min)

1. In Render → `roastgpt-api` → **Shell** tab.
2. Run:
   ```bash
   ADMIN_EMAIL=you@yourdomain.com \
   ADMIN_PASSWORD=YourStrongPass123! \
     python -m scripts.bootstrap_admin
   ```
3. You should see: `[OK] Created admin user: you@yourdomain.com (id=1)`

> 🔐 **Use a real email and a 12+ character password.** This is your super-admin account.

---

### Step 5 · Deploy the frontend to Vercel (5 min)

1. Go to https://vercel.com → **Add New** → **Project**.
2. Import the `AI-ROSTER` GitHub repo.
3. Set **Root Directory** to `frontend`.
4. Framework auto-detects as **Next.js**.
5. Under **Environment Variables**, add:
   ```
   NEXT_PUBLIC_API_URL = https://roastgpt-api.onrender.com
   ```
6. Click **Deploy**. Vercel builds and gives you a URL like `https://ai-roster.vercel.app`.

---

### Step 5b · Wire up CORS (1 min)

Now that you have the Vercel URL, go back to **Render → `roastgpt-api` → Environment** and update:
```
ALLOWED_ORIGINS = https://ai-roster.vercel.app,https://www.yourdomain.com
```

Click **Save**. Render redeploys.

> ✅ Without this, the browser blocks every API call with a CORS error.

---

### Step 6 · Configure the Razorpay webhook (2 min)

1. Razorpay Dashboard → Settings → Webhooks → **Add new**.
2. **URL**: `https://roastgpt-api.onrender.com/api/payments/webhook`
3. **Active events**: `payment.captured` · `payment.failed` · `subscription.cancelled`
4. **Secret**: paste the same value you put in `RAZORPAY_WEBHOOK_SECRET`
5. **Save**.

Test: trigger a test payment, then check Render → Logs for `webhook received`.

---

### Step 7 · Smoke test (2 min)

```bash
# Backend health
curl https://roastgpt-api.onrender.com/api/health
# Expected: {"status":"ok","library_loaded":true,"roasts":336,...}

# System status
curl https://roastgpt-api.onrender.com/api/v1/system/status
# Expected: status=healthy, database=ok, redis=ok

# Plans
curl https://roastgpt-api.onrender.com/api/payments/plans
# Expected: 3 plans
```

Open `https://ai-roster.vercel.app` in your browser and:
- [ ] Landing page loads
- [ ] Register a new account
- [ ] Login works
- [ ] `/chat` sends a message and gets a roast
- [ ] `/pricing` shows 3 plans
- [ ] `/leaderboard` shows entries
- [ ] `/account` loads with your profile fields filled
- [ ] `/stats` shows your score breakdown
- [ ] `/admin` works (you are the bootstrapped admin)

---

### Step 8 · Custom domain (optional, 10 min)

#### Domain registrar → Namecheap / Cloudflare / GoDaddy
Buy `yourdomain.com` (~$10/yr) or `yourdomain.in` (~$5/yr).

#### Vercel (frontend)
- Settings → Domains → Add `yourdomain.com` and `www.yourdomain.com`
- Vercel gives you the A / CNAME records. Add them at your registrar.

#### Render (backend)
- Settings → Custom Domains → Add `api.yourdomain.com`
- Render gives you a CNAME. Add it at your registrar.

#### Wait for DNS propagation
Usually 5–30 minutes; max 48 hours.

#### Update env vars
| Service | Variable | New value |
|---------|----------|-----------|
| Render | `ALLOWED_ORIGINS` | `https://yourdomain.com,https://www.yourdomain.com` |
| Render | `FRONTEND_URL` | `https://yourdomain.com` |
| Vercel | `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com` |
| Razorpay | Webhook URL | `https://api.yourdomain.com/api/payments/webhook` |

---

### Step 9 · Switch Razorpay to LIVE mode (when you want real money)

> ⚠️ **Test mode is for development only.** Do not switch to live until you've tested the full payment flow with test cards.

1. Razorpay Dashboard → **Toggle "Live mode" ON**.
2. Settings → API Keys → Generate **Live** key.
3. Replace in Render env:
   ```
   RAZORPAY_KEY_ID = rzp_live_xxx
   RAZORPAY_KEY_SECRET = <live secret>
   ```
4. Update webhook URL in Razorpay dashboard to the production URL.
5. Set up business KYC (PAN, bank account, GST if applicable) in Razorpay.
6. Test a ₹1 transaction end-to-end.

---

### Step 10 · Post-launch (1 hour)

- [ ] **Sentry** → check no errors in first hour
- [ ] **UptimeRobot** (https://uptimerobot.com, free) → monitor `https://api.yourdomain.com/api/health` every 5 min
- [ ] **Google Analytics 4** → add `G-XXXXXXX` to `frontend/.env` as `NEXT_PUBLIC_GA_ID`
- [ ] **Google Search Console** → submit `https://yourdomain.com/sitemap.xml`
- [ ] **Google AdSense** → apply (need 1K+ daily visitors for approval; revenue kicks in after)
- [ ] **Status page** (free at https://statuspage.io) → link from footer
- [ ] **Cron-job.org** → ping your backend every 14 min so it never cold-starts

---

## 📈 Marketing Checklist (the "earn from it" part)

- [ ] **Post on Product Hunt** (https://producthunt.com) — best single day of traffic you'll ever get
- [ ] **Show HN** — https://news.ycombinator.com/show
- [ ] **Reddit**: r/SideProject, r/IndieHackers, r/Entrepreneur, r/Chatbots, r/SaaS
- [ ] **Twitter / X**: thread with a 30s demo video
- [ ] **LinkedIn**: founders love a "I built this" post
- [ ] **IndieHackers.com**: post the build-in-public journey
- [ ] **Dev.to**: write a 5-min "How I built this" article
- [ ] **SEO blog posts**: "AI roast generator", "best roast AI", "savage chatbot"
- [ ] **YouTube Shorts / Instagram Reels**: 30s demo = 100K+ views possible
- [ ] **Hacker Newsletter**: https://hackernewsletter.com (paid but worth it)

---

## 📁 Project Structure

```
AI-ROSTER/
├── README.md                       # ← you are here
├── DEPLOY.md                       # detailed deployment runbook
├── ROAST_LIBRARY.md                # roast template engine design
├── render.yaml                     # Render Blueprint
├── vercel.json                     # Vercel config (HSTS, CSP, headers)
├── .env.example                    # every env var documented
├── LICENSE                         # proprietary license
│
├── roast-library/                  # 187 hand-written roasts
│   ├── schema.json
│   ├── openers.json (9)
│   ├── closers.json (6)
│   └── roasts/   # 8 mode JSON files
│
├── backend/                        # FastAPI engine
│   ├── main.py                     # lifespan: sentry → cache → queue → DB
│   ├── runtime.txt                 # 3.12.7
│   ├── requirements.txt
│   ├── scripts/                    # backup, restore, list_db, bootstrap_admin
│   ├── app/
│   │   ├── auth.py                 # JWT + bcrypt + RBAC
│   │   ├── auth_routes.py          # /api/auth/*
│   │   ├── auth_schemas.py         # Pydantic v2
│   │   ├── admin_routes.py         # /api/admin/* (RBAC-gated)
│   │   ├── routes.py               # /api/session/*
│   │   ├── history_routes.py       # /api/history
│   │   ├── payment_routes.py       # /api/payments/*
│   │   ├── leaderboard_routes.py
│   │   ├── db_models.py            # 13 tables
│   │   ├── cache.py                # Redis + in-memory
│   │   ├── queue.py                # Celery + in-memory
│   │   ├── monitoring.py           # Sentry + JSON logging
│   │   ├── round9_routes.py        # contact / notifications / system
│   │   ├── jobs.py                 # 3 background tasks
│   │   ├── models.py               # response models
│   │   ├── utils.py                # feature flags + sanitizers + emails
│   │   └── filler.py               # placeholder types
│   └── tests/                      # 434 tests
│
└── frontend/                       # Next.js 14 chat UI
    ├── app/
    │   ├── page.tsx                # landing
    │   ├── chat/[sessionId]/       # chat client
    │   ├── login/  register/  forgot-password/  reset-password/  verify-email/
    │   ├── pricing/                # 3 plans + Razorpay
    │   ├── account/                # profile · subscription · payments
    │   ├── history/                # messages + sessions
    │   ├── admin/                  # 10-tab dashboard
    │   ├── leaderboard/            # public weekly/monthly/all-time
    │   ├── achievements/           # 15 badges
    │   ├── stats/                  # personal user stats
    │   ├── share/[id]/             # public share view
    │   ├── about/  faq/  changelog/  contact/  developers/  status/
    │   ├── terms/  privacy/
    │   └── not-found.tsx · error.tsx · loading.tsx
    ├── components/                 # HeaderAuth · ScorePanel · NotificationBell · CookieBanner
    ├── lib/                        # api.ts · auth-api.ts · types.ts · errors.ts
    └── tests/                      # Vitest
```

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        BROWSER                              │
│  Next.js 14 SPA  ──  Bearer JWT in sessionStorage  ───┐    │
└──────────────────────────────────────────────────────┼────┘
                                                       │ HTTPS JSON
┌──────────────────────────────────────────────────────▼────┐
│                    FastAPI Backend (gunicorn)             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
│  │  Auth      │  │  Sessions  │  │  Payments  │         │
│  │  RBAC      │  │  Roast     │  │  Webhooks  │         │
│  │  RateLimit │  │  Engine    │  │  Plans     │         │
│  └────────────┘  └────────────┘  └────────────┘         │
│         │                │                │              │
│  ┌──────▼────────────────▼────────────────▼──────┐       │
│  │              SQLAlchemy 2.0 ORM                │       │
│  └─┬──────────┬──────────┬──────────┬──────────┬─┘       │
│    │          │          │          │          │         │
│    ▼          ▼          ▼          ▼          ▼         │
│  Neon PG   Upstash    Sentry    In-proc    SMTP          │
│  (data)    Redis      (errors)  Queue     (emails)       │
│  (0.5GB)   (cache)               (jobs)    (Resend)      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  Render Cron (daily)  │
              │  → JSON dump          │
              │  → GitHub backup repo │
              └───────────────────────┘
```

---

## 🔒 Security Posture (built-in)

These defenses are on by default. **Don't disable them in production.**

- **Secret validation at startup** — refuses to boot if `JWT_SECRET_KEY` / `ADMIN_API_KEY` are dev defaults in `ENVIRONMENT=production`.
- **JWT claims** — `sub`, `exp`, `iat`, `jti`, `ver` (token_version). Password change / admin deactivation instantly invalidates every other session.
- **Algorithm allow-list** — only HS256 / HS384 / HS512. Decoding also has 30s leeway for clock skew.
- **Timing-safe login** — unknown email still runs bcrypt to defeat user-enumeration.
- **CORS** — explicit `ALLOWED_ORIGINS` allow-list, no wildcards with credentials.
- **Rate limiting** — per-IP · per-endpoint · per-user, 3 tiers. `X-Forwarded-For` only honored if the direct peer is in `TRUSTED_PROXIES`.
- **Body size cap** — `MAX_BODY_BYTES` (5 MB default) → 413 before route runs.
- **Free-tier atomicity** — `UPDATE … WHERE free_messages_used < 5` so two parallel requests can't both pass.
- **Webhook idempotency** — unique index on `razorpay_payment_id`, duplicates rejected.
- **Subscription uniqueness** — only one `active` / `past_due` per user, enforced on create / grant / webhook.
- **Stored XSS** — all user text through `sanitize_text` (strips angle brackets, control chars, URLs in public display names).
- **Email masking** — `al***@example.com` everywhere public.
- **In-memory session caps** — oldest live session evicted at `ROASTGPT_MAX_SESSIONS` overflow.

---

## 📈 Roadmap

- [x] Round 1–5: Core chat, auth, payments, leaderboard
- [x] Round 6: LLM fallback (OpenAI / Anthropic / stub)
- [x] Round 7: RBAC + audit log + monitoring
- [x] Round 8: Redis cache + Celery queue + Sentry
- [x] Round 9: Contact, notifications, system status, activity, broadcast
- [x] Round 9b: Frontend-backend integration audit (7 bugs fixed)
- [ ] Round 10: WebSocket streaming responses
- [ ] Round 11: Voice input/output
- [ ] Round 12: Public API + developer keys
- [ ] Round 13: Mobile app (React Native)

---

## 🤝 Contributing

This is a **proprietary** project owned by **MIHIR K PATEL**. Pull requests are **not accepted** from the public. If you found a security issue, please email **security@roastgpt.app** (do not open a public issue).

If you're interested in a commercial license, partnership, or white-label deployment, contact the author directly.

---

## 📜 License

```
═══════════════════════════════════════════════════════════════════
  ROASTGPT — Proprietary Software
  Copyright © 2024–2026 MIHIR K PATEL. All Rights Reserved.
═══════════════════════════════════════════════════════════════════

  This software and associated documentation files (the "Software")
  are the exclusive property of MIHIR K PATEL.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
  OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
  NONINFRINGEMENT.

  You may NOT:
    ✗ Copy, reproduce, or duplicate the source code
    ✗ Modify, merge, or create derivative works
    ✗ Distribute, sublicense, sell, or transfer the Software
    ✗ Reverse engineer, decompile, or disassemble the Software
    ✗ Use the Software for commercial purposes without written
      permission from MIHIR K PATEL
    ✗ Remove or alter any copyright, trademark, or proprietary
      notices contained in or accompanying the Software

  You MAY:
    ✓ View the source code for personal, non-commercial evaluation
    ✓ Submit a written request to license@roastgpt.app for a
      commercial license
    ✓ Reference this project in articles, tutorials, or academic
      papers with proper attribution

  See the LICENSE file for the full proprietary license text.

  Violations will be prosecuted to the maximum extent permitted by
  applicable law, including under the Indian Copyright Act, 1957,
  the Information Technology Act, 2000, the DMCA, and the Berne
  Convention for the Protection of Literary and Artistic Works.
═══════════════════════════════════════════════════════════════════
```

---

## 👤 Author

<div align="center">

<img src="https://img.shields.io/badge/Author-MIHIR_K_PATEL-gold?style=for-the-badge" alt="Author"/>

**MIHIR K PATEL**

Full-Stack Engineer · AI/ML · SaaS Architect

<a href="https://github.com/mihir2452005"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"/></a>
<a href="https://linkedin.com/in/mihir2452005"><img src="https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn"/></a>
<a href="https://twitter.com/mihir2452005"><img src="https://img.shields.io/badge/Twitter-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white" alt="Twitter"/></a>
<a href="mailto:hello@roastgpt.app"><img src="https://img.shields.io/badge/Email-EA4335?style=for-the-badge&logo=gmail&logoColor=white" alt="Email"/></a>
<a href="https://roastgpt.app"><img src="https://img.shields.io/badge/Website-FF6B6B?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Website"/></a>

</div>

---

## 🙏 Acknowledgements

Built with the help of:

- [FastAPI](https://fastapi.tiangolo.com) — the best Python web framework
- [Next.js](https://nextjs.org) — React framework for production
- [Neon](https://neon.tech) — serverless PostgreSQL
- [Upstash](https://upstash.com) — serverless Redis
- [Render](https://render.com) — hassle-free app hosting
- [Vercel](https://vercel.com) — frontend deployment
- [Razorpay](https://razorpay.com) — Indian payment gateway
- [Sentry](https://sentry.io) — error monitoring
- [Resend](https://resend.com) — modern transactional email

---

## ⭐ Star History

<div align="center">

<a href="https://star-history.com/#mihir2452005/AI-ROSTER&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mihir2452005/AI-ROSTER&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=mihir2452005/AI-ROSTER&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=mihir2452005/AI-ROSTER&type=Date" />
  </picture>
</a>

</div>

---

<div align="center">

### 💀 "Chat. Get Roasted. Cry. Repeat." 💀

**Made with 🔥 by [MIHIR K PATEL](https://github.com/mihir2452005)**

<sub>This README, the source code, the design, the architecture, the brand, the copy, and every roasty string in the database is the intellectual property of MIHIR K PATEL. If you fork it, link back. If you copy it, expect a DMCA.</sub>

<br/>

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,28,40&height=100&section=footer"/>

</div>
