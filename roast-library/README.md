# Roast Library

> The content foundation for RoastGPT — 183 pre-written roasts that handle ~80% of traffic without any LLM call.

The full design rationale lives in [`../ROAST_LIBRARY.md`](../ROAST_LIBRARY.md). This README is a quick orientation for engineers consuming these files.

## Files

```
roast-library/
├── README.md                    # this file
├── schema.json                  # JSON Schema for validating roast templates
├── intents.json                 # intent detection rules (6 intents + scoring)
├── personalities.json           # 6 personality voices with damage ranges
├── scores.json                  # session score calculation rules
├── openers.json                 # first roast of a session
├── comebacks.json               # when user tries to clap back
├── closers.json                 # final burn at end of session
├── callbacks.json               # "welcome back" roasts for returning users
└── roasts/
    ├── general.json             # fallback (10)
    ├── friendly.json            # 22
    ├── savage.json              # 24
    ├── programmer.json          # 27
    ├── student.json             # 26
    ├── gamer.json               # 24
    ├── corporate.json           # 24
    └── startup.json             # 26
```

**Total: ~183 roasts + 18 special-purpose templates.**

## Loading order

The engine should load files in this order at startup:

1. `schema.json` — to validate the others.
2. `intents.json` — to build the keyword index.
3. `personalities.json` — to load the 6 voices.
4. `scores.json` — to know how to compute session scores.
5. `openers.json`, `comebacks.json`, `closers.json`, `callbacks.json` — special-purpose pools.
6. All files in `roasts/*.json` — the main content pool.

## Matching a roast (cheat sheet)

```python
def select_roast(user_message, user_context, session):
    intents = detect_intent(user_message)              # uses intents.json
    pool = load_roasts(user_context.mode)               # e.g. roasts/savage.json
    pool = filter_by_personality(pool, user_context.personality)
    pool = filter_by_damage_range(pool, user_context.personality)
    pool = filter_by_intent(pool, intents)
    chosen = weighted_random(pool, key="match_score")
    return fill_placeholders(chosen, user_context, session)
```

Full algorithm: see `ROAST_LIBRARY.md` §9.

## Adding a new roast

1. Pick the right `roasts/<mode>.json` file.
2. Match the schema in `schema.json`. Run the validator before commit.
3. Use a unique `id` matching `<mode>_<number>`.
4. Set `damage` (1–10), `tone` (light/playful/dry/cutting/brutal), and at least one `personalities` entry.
5. If you use placeholders, define each one in the `placeholders` object.
6. Pass the quality checklist in `ROAST_LIBRARY.md` §13.

```bash
# Validate a single file
npx ajv-cli validate -s schema.json -d roasts/savage.json --spec=draft7

# Validate everything
for f in roasts/*.json; do
  npx ajv-cli validate -s schema.json -d "$f" --spec=draft7 || echo "FAIL: $f"
done
```

## Safety rules (non-negotiable)

- Never add a roast that targets protected classes (race, religion, gender, sexuality, disability, nationality).
- Never reference real private individuals.
- Never encourage self-harm or harm to others.
- Savage roasts must remain punchy, not cruel.

The "staying within safe boundaries" line in the product spec is enforced here, at the library level. Roasts that violate this should be rejected in review, not just moderated at runtime.

## Current coverage

| Intent       | Roasts eligible | Notes |
|--------------|-----------------|-------|
| programming  | ~50             | across programmer, savage, general, corporate |
| school       | ~30             | across student, savage, general |
| gaming       | ~30             | across gamer, savage, general |
| fitness      | ~10             | fallback to general — Phase 2 target |
| money        | ~25             | across startup, corporate, savage |
| relationships| ~10             | fallback to general — Phase 2 target |
| career       | ~45             | across corporate, startup, programmer |
| general      | 10              | explicit fallback |

Phase 2 target: every intent + every personality combo should have at least 3 eligible roasts.
