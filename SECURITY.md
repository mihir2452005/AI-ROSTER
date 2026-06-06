# Security Policy

## ⚖️ Copyright & License

**RoastGPT** is proprietary software owned exclusively by **MIHIR K PATEL**.

The source code is published on GitHub for **viewing and personal
evaluation** only. It is **NOT** open source, **NOT** MIT, **NOT** Apache,
and **NOT** in the public domain.

Unauthorized copying, modification, redistribution, or commercial use
is **strictly prohibited** and will be enforced under:

- Indian Copyright Act, 1957
- Information Technology Act, 2000
- Berne Convention for the Protection of Literary and Artistic Works
- DMCA (United States)
- EU Copyright Directive (2001/29/EC)

See [LICENSE](../LICENSE) for the full proprietary license text.

---

## 🔒 Supported Versions

Only the latest commit on the `main` branch receives security updates.

| Branch   | Supported |
|----------|:---------:|
| `main`   |    ✅     |
| any fork |    ❌     |
| any older commit | ❌ |

---

## 🚨 Reporting a Vulnerability

If you discover a security issue in the deployed RoastGPT application
(hosted at https://roastgpt.app or related domains):

- **Email:** security@roastgpt.app
- **Subject line:** `[SECURITY] <short description>`
- **Response SLA:** 48 hours
- **PGP fingerprint:** *(available on request)*

### What to include

1. The URL or endpoint affected
2. Steps to reproduce (a curl command or a screenshot)
3. The impact (data exposure, RCE, XSS, etc.)
4. Your name and how you'd like to be credited (or "anonymous")

### What to expect

- An acknowledgement within 48 hours
- A triage decision within 7 days
- A fix or mitigation within 30 days for high-severity issues
- Public disclosure only after a fix is deployed

### ⚠️ Important: do NOT

- File a public GitHub issue for a security vulnerability
- Disclose the issue publicly before a fix is shipped
- Test the vulnerability against production without permission
- Access, modify, retain, or transfer any user data you encounter

Safe harbour: Good-faith security research that follows this policy
will not be the subject of legal action by the Author.

---

## 🛡️ Built-in Security (production posture)

| Defense | Where | Default |
|---------|-------|---------|
| JWT with `token_version` | `app/auth.py` | ✅ on |
| HS256/384/512 only | `app/auth.py` | ✅ on |
| bcrypt cost = 12 | `app/auth.py` | ✅ on |
| Per-IP rate limit | `main.py` | 60 req / 60 s |
| Per-endpoint rate limit | `main.py` | register 5/min, login 10/min, contact 10/min |
| CORS explicit allow-list | `main.py` | `ALLOWED_ORIGINS` env |
| Trusted-proxy XFF check | `main.py` | `TRUSTED_PROXIES` env |
| Body-size cap | `main.py` | 5 MB (returns 413) |
| Stored XSS sanitizer | `app/sanitize.py` | ✅ on |
| Email masking | `app/sanitize.py` | ✅ on |
| Webhook signature verify | `app/payment_routes.py` | HMAC-SHA256 |
| Webhook idempotency | DB unique index | ✅ on |
| Subscription uniqueness | DB unique partial index | ✅ on |
| Free-tier atomicity | `UPDATE … WHERE < 5` | ✅ on |
| Secret strength check | startup | fails fast in prod |
| Sentry PII scrubber | `app/monitoring.py` | ✅ on |
| In-memory session cap | `ROASTGPT_MAX_SESSIONS` | 10 000 |
| Memory cap per user | `ROASTGPT_MAX_MEM_USERS` | 10 000 |
| Maintenance mode | `main.py` middleware | admin-gated |
| Login timing | dummy bcrypt on unknown email | ✅ on |
| Token storage | `sessionStorage` (not `localStorage`) | ✅ on |
| HTTP security headers | `vercel.json` | HSTS, CSP, X-Frame-Options, Permissions-Policy |

---

## 🔐 Secret Handling — for the operator

**Never** commit `.env`, `*.db`, or any file containing real secrets.

The repo ships with `.env.example` (placeholders only) and `.gitignore`
blocks common secret patterns. Before pushing:

```bash
git status --ignored
grep -r "rzp_live_\|ghp_\|sk_live_\|AKIA" . --include="*.py" --include="*.ts" --include="*.tsx" --include="*.md" --include="*.json"
```

If you ever leak a secret:

1. **Rotate it immediately** in the source service (Razorpay, GitHub, etc.)
2. **Update the env var** on Render
3. **Audit the access logs** in the source service
4. **Force-restart** the web service
5. **Add `git filter-repo`** to scrub the secret from history if committed

---

## 📧 Contact

| Topic             | Email                  |
|-------------------|------------------------|
| Vulnerability     | security@roastgpt.app  |
| Copyright claim   | copyright@roastgpt.app |
| License request   | licensing@roastgpt.app |
| General           | hello@roastgpt.app     |

---

*Copyright © 2024–2026 MIHIR K PATEL. All Rights Reserved.*
