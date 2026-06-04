# RoastGPT Backend

> FastAPI engine that consumes `../roast-library/` and exposes a chat-style API.

## Quick start

```bash
# From this directory:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run dev server
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the interactive API explorer.

## Layout

```
backend/
├── main.py              # FastAPI app + lifespan
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── config.py        # library path, engine settings
│   ├── models.py        # Pydantic schemas (library + API)
│   ├── library.py       # loads + validates roast-library/ at startup
│   ├── intent.py        # keyword + phrase intent detection
│   ├── filler.py        # placeholder resolution (5 types)
│   ├── matcher.py       # candidate filtering + scoring + weighted pick
│   ├── scorer.py        # session score calculation
│   ├── session.py       # in-memory session store + user memory
│   └── routes.py        # /api/* endpoints
└── tests/
    └── test_smoke.py    # full-flow smoke tests
```

## API

| Method | Path                              | Purpose |
|--------|-----------------------------------|---------|
| GET    | `/api/health`                     | Liveness + library stats |
| GET    | `/api/modes`                      | Available roast modes |
| GET    | `/api/personalities`              | Available personality voices |
| POST   | `/api/session/start`              | Create session, return opener |
| POST   | `/api/session/{id}/roast`         | Send a user message, get roasted |
| POST   | `/api/session/{id}/end`           | End session, return closer + scores |
| GET    | `/api/session/{id}`               | Inspect session state |

### Example

```bash
# Start a session
curl -X POST http://localhost:8000/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "savage", "personality": "savage_one", "username": "Alice"}'

# Send a message
curl -X POST http://localhost:8000/api/session/<SID>/roast \
  -H "Content-Type: application/json" \
  -d '{"message": "My code has 47 bugs in production"}'

# End
curl -X POST http://localhost:8000/api/session/<SID>/end
```

## Tests

```bash
pytest
```

Smoke tests cover: library loads, health, full session flow, intent detection,
comeback detection, placeholder filling, friendly mode damage range, and
unknown-session 404.

## What's in memory vs persistent

| Thing               | MVP storage   | Production target |
|---------------------|---------------|-------------------|
| Sessions            | in-memory dict | Redis (Upstash) |
| User memory         | in-memory dict | PostgreSQL (Supabase) |
| Roast library       | JSON on disk   | same, or DB-backed |
| Auth (not in MVP)   | none           | JWT |

The `SessionStore` and `UserMemory` classes in `app/session.py` are the
swappable seams. Replace their internals; the rest of the engine doesn't
care.

## Performance notes

The whole template layer is pure string + dict operations. A single roast
turn should be **under 5ms** on a warm cache. The 1% of traffic that
escalates to the LLM layer (not yet implemented) is the only place we
expect to see real latency.

## Next steps

1. Wire up Redis for session state.
2. Wire up PostgreSQL for user memory + share URLs.
3. Add JWT auth.
4. Add Layer 2 (dynamic roast builder) and Layer 3 (LLM fallback).
5. Build the Next.js frontend that consumes this API.
