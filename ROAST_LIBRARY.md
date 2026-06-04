# RoastGPT — Roast Template Library

> Design document for the 90%-of-traffic template layer.
> This is the **content foundation** of the entire product.

---

## 1. Overview

The roast library is a structured collection of pre-written roast templates. The roast engine:

1. Detects **intent** from the user's message (e.g. "programming", "school").
2. Selects a **roast mode** the user picked (e.g. "Savage", "Programmer").
3. Optionally applies a **personality** voice (e.g. "The Professor").
4. Matches and **fills placeholders** in a template.
5. Returns the final roast in milliseconds — no LLM call needed.

Only when the template layer can't find a confident match (the remaining ~10%) does the system escalate to dynamic builders or LLM fallback.

**Goal:** 500+ high-quality templates at launch, covering all 8 modes and 6 personalities, with enough variety that no two consecutive roasts feel repetitive. Current count is in §12.

---

## 2. Directory Structure

```
roast-library/
├── README.md                       # this file
├── schema.json                     # JSON Schema for validation
├── intents.json                    # intent detection rules
├── personalities.json              # personality definitions
├── scores.json                     # score calculation rules
├── openers.json                    # "welcome" / "first message" roasts
├── comebacks.json                  # "you tried to clap back" roasts
├── closers.json                    # session-end final burns
├── callbacks.json                  # "remember when you said X" roasts
└── roasts/
    ├── general.json                # fallback when no intent matches
    ├── friendly.json
    ├── savage.json
    ├── programmer.json
    ├── student.json
    ├── gamer.json
    ├── corporate.json
    └── startup.json
```

---

## 3. Master JSON Schema

Every roast template follows this shape. JSON Schema file lives at `schema.json` for validation.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RoastTemplate",
  "type": "object",
  "required": ["id", "mode", "personalities", "template", "damage"],
  "properties": {
    "id":              { "type": "string", "pattern": "^[a-z]+_[0-9]{3,}$" },
    "mode":            { "enum": ["friendly", "savage", "programmer", "student", "gamer", "corporate", "startup", "general"] },
    "subcategory":     { "type": "string" },
    "personalities":   { "type": "array", "items": { "enum": ["savage_one", "sarcastic_friend", "toxic_interviewer", "startup_investor", "professor", "gamer"] } },
    "intents":         { "type": "array", "items": { "type": "string" } },
    "keywords":        { "type": "array", "items": { "type": "string" } },
    "trigger_phrases": { "type": "array", "items": { "type": "string" } },
    "damage":          { "type": "integer", "minimum": 1, "maximum": 10 },
    "tone":            { "enum": ["light", "playful", "dry", "cutting", "brutal"] },
    "context_tags":    { "type": "array", "items": { "type": "string" } },
    "template":        { "type": "string", "minLength": 10 },
    "placeholders":    {
      "type": "object",
      "additionalProperties": {
        "oneOf": [
          { "type": "array", "minItems": 1 },
          { "type": "object",
            "required": ["type"],
            "properties": {
              "type":   { "enum": ["enum", "context", "intent", "history", "username"] },
              "values": { "type": "array" },
              "default":{ "type": "string" }
            }
          }
        ]
      }
    },
    "reaction":        { "type": "string" },
    "followup_id":     { "type": "string" },
    "weight":          { "type": "number", "minimum": 0, "maximum": 1, "default": 1.0 }
  }
}
```

### Field reference

| Field            | Purpose |
|------------------|---------|
| `id`             | Unique key. Format: `<mode>_<number>` (e.g. `prog_001`). |
| `mode`           | Which mode this roast belongs to. |
| `subcategory`    | Optional grouping inside a mode (e.g. "code_quality", "deadlines"). |
| `personalities`  | Which personalities may deliver this roast. Empty array = any. |
| `intents`        | Which intent tags should activate this roast. Empty = always eligible. |
| `keywords`       | Words/phrases that boost the match score if present. |
| `trigger_phrases`| Hard-match phrases (case-insensitive substring). |
| `damage`         | 1–10. Used by score system. |
| `tone`           | Style tag for filtering. |
| `context_tags`   | Free-form tags: `humor:meta`, `topic:tech`, `style:metaphor`, etc. |
| `template`       | The roast with `{placeholder}` slots. |
| `placeholders`   | Maps each slot to its possible values or context source. |
| `reaction`       | Optional emoji suffix. |
| `followup_id`    | Optional id of a roast to chain after this one. |
| `weight`         | Selection probability (1.0 = default, lower = rarer). |

### Placeholder types

- `enum`      → pick randomly from `values` (default if no other source matches).
- `context`   → use runtime context (e.g. "this morning's coffee").
- `intent`    → use the detected intent topic (e.g. "your code").
- `history`   → pull from user's prior sessions (last roast, last topic).
- `username`  → the user's display name.

---

## 4. Intent Detection System

File: `intents.json`

The intent detector scans the user message and assigns a weighted score to each intent. Top intent wins (or top N intents if we want a blended roast later).

```json
{
  "intents": {
    "programming": {
      "label": "Programming",
      "weight": 1.0,
      "keywords": [
        "code", "coding", "program", "developer", "dev", "function", "variable",
        "bug", "compile", "compile error", "syntax", "git", "commit", "push",
        "pull request", "PR", "merge", "deploy", "deployment", "API", "endpoint",
        "frontend", "backend", "fullstack", "frontend developer", "backend developer",
        "javascript", "typescript", "python", "java", "c++", "rust", "go", "react",
        "next.js", "node", "django", "flask", "fastapi", "docker", "kubernetes",
        "aws", "azure", "gcp", "sql", "nosql", "mongodb", "postgres", "redis",
        "leetcode", "hackerrank", "stackoverflow", "stack overflow", "ide",
        "vscode", "intellij", "production", "prod", "staging", "localhost"
      ],
      "phrases": [
        "my code doesn't work", "why won't it compile", "merge conflict",
        "i wrote a function", "i'm a developer", "i'm a software engineer",
        "i work in tech", "stack overflow said", "production is down"
      ]
    },
    "school": {
      "label": "School",
      "weight": 1.0,
      "keywords": [
        "school", "class", "classes", "course", "courses", "exam", "exams",
        "test", "tests", "quiz", "quizzes", "homework", "assignment",
        "assignments", "essay", "essays", "thesis", "dissertation", "gpa",
        "professor", "prof", "teacher", "lecture", "lectures", "study",
        "studying", "studied", "degree", "major", "minor", "university",
        "college", "campus", "dorm", "semester", "term", "year", "freshman",
        "sophomore", "junior", "senior", "graduate", "undergrad", "phd",
        "masters", "bachelors", "dropout", "academic", "academia", "library"
      ],
      "phrases": [
        "i have an exam tomorrow", "i failed my test", "i skipped class",
        "i'm in college", "i'm a student", "my professor", "my gpa",
        "i didn't study", "i have homework", "my essay"
      ]
    },
    "gaming": {
      "label": "Gaming",
      "weight": 1.0,
      "keywords": [
        "game", "games", "gaming", "gamer", "play", "playing", "console",
        "pc", "ps5", "playstation", "xbox", "nintendo", "switch", "steam",
        "ranked", "rank", "competitive", "casual", "fps", "moba", "mmo",
        "rpg", "loot", "loot box", "grind", "grinding", "raid", "boss",
        "league", "valorant", "csgo", "cs2", "fortnite", "apex", "overwatch",
        "wow", "minecraft", "elden ring", "dark souls", "k/d", "kd ratio",
        "kda", "headshot", "clutch", "no scope", "sniper", "tank", "dps",
        "support", "healer", "jungle", "lane", "meta", "tier list", "nerf",
        "buff", "patch", "dlc", "speedrun", "esports", "twitch", "streamer"
      ],
      "phrases": [
        "i got destroyed", "i lost rank", "i got matched against",
        "my team is trash", "i got kicked", "i clutched", "i rage quit"
      ]
    },
    "fitness": {
      "label": "Fitness",
      "weight": 0.9,
      "keywords": [
        "gym", "workout", "lifting", "weights", "cardio", "run", "running",
        "marathon", "bench", "squat", "deadlift", "rep", "reps", "set",
        "sets", "muscle", "abs", "bulk", "cut", "bulking", "cutting",
        "protein", "creatine", "pre-workout", "calories", "diet", "keto",
        "intermittent fasting", "weight loss", "weight gain", "fat loss"
      ],
      "phrases": [
        "i skipped leg day", "i can't lift", "i'm bulking", "i'm cutting",
        "i missed my workout"
      ]
    },
    "money": {
      "label": "Money",
      "weight": 0.8,
      "keywords": [
        "money", "cash", "rich", "wealthy", "broke", "salary", "wage",
        "income", "revenue", "profit", "loss", "invest", "investing",
        "investment", "stocks", "crypto", "bitcoin", "ethereum", "nft",
        "trading", "trader", "wall street", "hedge fund", "ipo", "loan",
        "debt", "credit", "mortgage", "rent", "budget", "savings", "401k",
        "ira", "roth", "tax", "taxes", "audit", "side hustle", "freelance"
      ],
      "phrases": [
        "i'm broke", "i'm getting paid", "i got fired", "i got laid off",
        "i got promoted", "my salary", "i invested"
      ]
    },
    "relationships": {
      "label": "Relationships",
      "weight": 0.7,
      "keywords": [
        "girlfriend", "boyfriend", "partner", "wife", "husband", "ex",
        "crush", "dating", "date", "tinder", "bumble", "hinge", "match",
        "relationship", "marriage", "married", "divorce", "single",
        "lonely", "love", "breakup", "dumped", "ghosted", "cheated",
        "friend", "friends", "best friend", "enemy", "enemies", "drama"
      ],
      "phrases": [
        "my ex", "my girlfriend", "my boyfriend", "i got ghosted",
        "i got dumped", "i'm single", "i'm married"
      ]
    },
    "career": {
      "label": "Career",
      "weight": 0.8,
      "keywords": [
        "job", "work", "career", "boss", "manager", "coworker", "office",
        "remote", "wfh", "linkedin", "resume", "cv", "interview",
        "hired", "fired", "promotion", "raise", "quit", "resign", "fired",
        "corporate", "startup", "employee", "employer", "company"
      ],
      "phrases": [
        "i hate my job", "i got fired", "i got promoted", "my boss",
        "i'm interviewing", "i quit", "linkedin told me"
      ]
    }
  },
  "fallback_intent": "general",
  "scoring": {
    "exact_phrase_match": 10,
    "keyword_match": 1,
    "decay_per_position": 0,
    "min_score_threshold": 1
  }
}
```

The detector is intentionally **simple and fast** (no embeddings, no LLM). It's a substring + phrase scanner. If no intent crosses the threshold, the roast engine falls back to the `general` mode.

---

## 5. Personality System

File: `personalities.json`

A personality wraps a roast with a voice — punctuation, prefix/suffix phrases, emoji style, and an opinionated tone that filters which roasts it will deliver.

```json
{
  "personalities": {
    "savage_one": {
      "label": "The Savage One",
      "description": "Maximum roast damage. No mercy.",
      "tone": "brutal",
      "min_damage": 6,
      "max_damage": 10,
      "allowed_modes": ["savage", "programmer", "student", "gamer", "corporate", "startup", "general"],
      "prefixes": ["Listen.", "Look.", "Real talk:", "Honestly?", ""],
      "suffixes": ["🔥", "💀", "🪦", "📉", "🗑️", ""],
      "signature_intro": "I'm not here to be your friend. I'm here to be honest.",
      "signature_outro": "And I won't even charge for the therapy."
    },
    "sarcastic_friend": {
      "label": "The Sarcastic Friend",
      "description": "Playful, loving, but cuts deep.",
      "tone": "playful",
      "min_damage": 3,
      "max_damage": 7,
      "allowed_modes": ["friendly", "savage", "programmer", "student", "gamer", "corporate", "startup", "general"],
      "prefixes": ["Oh honey,", "Sweetie,", "Babe,", "Listen here,", ""],
      "suffixes": ["❤️", "🥲", "😂", "🙃", ""],
      "signature_intro": "I'm saying this because I love you. That's the only reason.",
      "signature_outro": "Brunch Sunday. You're paying."
    },
    "toxic_interviewer": {
      "label": "The Toxic Interviewer",
      "description": "Acts like the world's toughest recruiter. Asks follow-ups.",
      "tone": "cutting",
      "min_damage": 5,
      "max_damage": 9,
      "allowed_modes": ["corporate", "startup", "programmer", "general"],
      "prefixes": ["So tell me,", "Interesting. Walk me through,", "And how does that make you feel,", "Help me understand,"],
      "suffixes": ["", "... moving on.", "Next question.", "We'll circle back."],
      "signature_intro": "Take a seat. We have a lot to cover.",
      "signature_outro": "We'll be in touch. We won't be in touch."
    },
    "startup_investor": {
      "label": "The Startup Investor",
      "description": "Destroys startup ideas with VC-speak.",
      "tone": "dry",
      "min_damage": 5,
      "max_damage": 9,
      "allowed_modes": ["startup", "corporate", "programmer", "general"],
      "prefixes": ["From a portfolio perspective,", "Let me be candid:", "If I may —", "Look,"],
      "suffixes": ["", "📉", "Not investable.", "Pass."],
      "signature_intro": "I have three minutes. Impress me. You won't.",
      "signature_outro": "I'll pass on this round. And every round after it."
    },
    "professor": {
      "label": "The Professor",
      "description": "Academically humiliates the user with citations.",
      "tone": "dry",
      "min_damage": 4,
      "max_damage": 8,
      "allowed_modes": ["student", "programmer", "general"],
      "prefixes": ["According to my research,", "As I always say,", "If you'd read the syllabus,", "Peer-reviewed evidence suggests,"],
      "suffixes": ["", "— and that's peer-reviewed.", "Citation needed.", "📚"],
      "signature_intro": "Class is in session. And you, my friend, are unprepared.",
      "signature_outro": "See me after class. Actually, don't."
    },
    "gamer": {
      "label": "The Gamer",
      "description": "Trash-talks like it's a ranked match.",
      "tone": "cutting",
      "min_damage": 5,
      "max_damage": 9,
      "allowed_modes": ["gamer", "programmer", "general"],
      "prefixes": ["Bro,", "No cap,", "Real talk,", "1v1 me,"],
      "suffixes": ["", "🕹️", "🎮", "GG.", "EZ."],
      "signature_intro": "You spawned into the wrong lobby.",
      "signature_outro": "Go next. The queue's waiting."
    }
  }
}
```

When a personality is active, the engine:

1. Filters roasts where `personalities` is non-empty and the current personality is in the list.
2. Filters roasts with `damage` outside `[min_damage, max_damage]`.
3. Optionally prepends a prefix and appends a suffix for flavor.
4. The first roast of a session may use `signature_intro`, the last `signature_outro`.

---

## 6. Roast Modes

The user picks a mode in the UI. Each mode has its own file under `roasts/`.

### 6.1 Mode — `general`

Fallback mode. Used when no other intent matches or the user picked "Custom" without context.

```json
{
  "mode": "general",
  "roasts": [
    {
      "id": "gen_001",
      "personalities": ["sarcastic_friend", "savage_one"],
      "intents": [],
      "damage": 4,
      "tone": "playful",
      "keywords": [],
      "template": "You have the energy of a {place}. I mean that as a compliment. Actually, no, I don't.",
      "placeholders": {
        "place": {
          "type": "enum",
          "values": ["mid-day Monday", "WiFi signal in a basement", "free trial antivirus", "loading screen of a person"]
        }
      },
      "reaction": "🙃"
    },
    {
      "id": "gen_002",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": [],
      "damage": 7,
      "tone": "brutal",
      "template": "I want to roast you, but I'm afraid the insults will feel personally attacked by how accurate they are.",
      "reaction": "🔥"
    },
    {
      "id": "gen_003",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "You're not stupid. You're just... enthusiastic about being wrong.",
      "reaction": "❤️"
    },
    {
      "id": "gen_004",
      "personalities": ["savage_one", "professor"],
      "intents": [],
      "damage": 8,
      "tone": "cutting",
      "template": "Your ancestors fought for your right to speak. They regret it daily.",
      "reaction": "🪦"
    },
    {
      "id": "gen_005",
      "personalities": ["sarcastic_friend", "gamer"],
      "intents": [],
      "damage": 5,
      "tone": "playful",
      "template": "You're like a {item} — present, technically functional, but no one really knows why.",
      "placeholders": {
        "item": {
          "type": "enum",
          "values": ["stock screensaver", "rubber doorstop", "decorative pillow", "USB cable that only charges one way"]
        }
      },
      "reaction": "😐"
    },
    {
      "id": "gen_006",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "If I had a dollar for every smart thing you said, I'd still need a payment plan.",
      "reaction": "💛"
    },
    {
      "id": "gen_007",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 9,
      "tone": "brutal",
      "template": "You're the reason group projects have a 'free-rider' clause.",
      "reaction": "📉"
    },
    {
      "id": "gen_008",
      "personalities": ["sarcastic_friend", "professor"],
      "intents": [],
      "damage": 4,
      "tone": "dry",
      "template": "You're proof that the bar was lowered. And then you tripped over it.",
      "reaction": "🤝"
    },
    {
      "id": "gen_009",
      "personalities": ["gamer", "savage_one"],
      "intents": [],
      "damage": 6,
      "tone": "cutting",
      "template": "You're like a {game} tutorial — everyone's stuck on you, and most want to skip.",
      "placeholders": {
        "game": {
          "type": "enum",
          "values": ["Dark Souls", "Linux", "Elden Ring", "IRS website", "Windows update"]
        }
      },
      "reaction": "🎮"
    },
    {
      "id": "gen_010",
      "personalities": ["sarcastic_friend", "savage_one"],
      "intents": [],
      "damage": 5,
      "tone": "playful",
      "template": "I don't roast people. I just describe you accurately and let the audience decide.",
      "reaction": "🎤"
    }
  ]
}
```

---

### 6.2 Mode — `friendly`

Light teasing. Safe to send to your mom. Damage 1–4 only.

```json
{
  "mode": "friendly",
  "roasts": [
    {
      "id": "frnd_001",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "I'd roast you, but my mom told me to be nice to people who are trying their best. 💛",
      "reaction": "💛"
    },
    {
      "id": "frnd_002",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 1,
      "tone": "light",
      "template": "You're the human equivalent of a typo — close, but not quite right. ✨",
      "reaction": "✨"
    },
    {
      "id": "frnd_003",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "Your vibe is giving 'participation trophy.' And honestly? It's kind of comforting. 🏆",
      "reaction": "🏆"
    },
    {
      "id": "frnd_004",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You're like a {item} — nobody's excited to see you, but life would feel weird without one.",
      "placeholders": {
        "item": {
          "type": "enum",
          "values": ["WiFi signal in a coffee shop", "tax refund", "default ringtone", "loading bar that lies"]
        }
      },
      "reaction": "🤗"
    },
    {
      "id": "frnd_005",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "You bring so much joy... to people who aren't related to you.",
      "reaction": "😊"
    },
    {
      "id": "frnd_006",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "If kindness were a currency, you'd be the world's richest {adjective} person.",
      "placeholders": {
        "adjective": {
          "type": "enum",
          "values": ["struggling", "lovably confused", "enthusiastically broke", "chronically optimistic"]
        }
      },
      "reaction": "💕"
    },
    {
      "id": "frnd_007",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 1,
      "tone": "light",
      "template": "You have a great face for radio. Wait, that wasn't nice. Let me restart. Your laugh is... memorable. 🎙️",
      "reaction": "🎙️"
    },
    {
      "id": "frnd_008",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "I was going to come up with a clever roast, but then I realized I'd be giving you too much credit.",
      "reaction": "🥲"
    },
    {
      "id": "frnd_009",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You're like a software update — nobody's excited, but we tolerate you. ☕",
      "reaction": "☕"
    },
    {
      "id": "frnd_010",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "Remember when you asked me to be honest? Yeah... let's not do that again.",
      "reaction": "💛"
    },
    {
      "id": "frnd_011",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You're the human equivalent of a {item} — I wouldn't go out of my way, but I won't say no.",
      "placeholders": {
        "item": {
          "type": "enum",
          "values": ["welcome mat", "default screensaver", "free sample", "buffer episode", "loyalty card"]
        }
      },
      "reaction": "🤗"
    },
    {
      "id": "frnd_012",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "Your vibe is the human version of a {weather} — not bad, just… present.",
      "placeholders": {
        "weather": {
          "type": "enum",
          "values": ["mid-March drizzle", "mild breeze", "cloudy with a chance of awkward", "Tuesday afternoon"]
        }
      },
      "reaction": "🌥️"
    },
    {
      "id": "frnd_013",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You're like a {snack} — nobody raves about you, but the bowl's always empty. Out of pity.",
      "placeholders": {
        "snack": {
          "type": "enum",
          "values": ["mixed nuts", "trail mix", "fruit cake", "the plain chips at the party"]
        }
      },
      "reaction": "🥜"
    },
    {
      "id": "frnd_014",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "You have the charisma of a {object}. A polite {object}. One that says sorry when you bump into it.",
      "placeholders": {
        "object": {
          "type": "enum",
          "values": ["library card", "waiting room magazine", "complimentary mint", "USB-C cable in a drawer"]
        }
      },
      "reaction": "📎"
    },
    {
      "id": "frnd_015",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "If I had to describe you in a movie, you'd be the friend who dies in the first act. Plot-wise. The audience will miss you briefly.",
      "reaction": "🎬"
    },
    {
      "id": "frnd_016",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You treat 'OK' like a personality. It works. Sort of. Three days a week.",
      "reaction": "👌"
    },
    {
      "id": "frnd_017",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "You are the human version of a {platform} — beloved by your mom, ignored by everyone else.",
      "placeholders": {
        "platform": {
          "type": "enum",
          "values": ["scrapbook", "pager", "fax machine", "Quibi", "Foursquare check-in"]
        }
      },
      "reaction": "📠"
    },
    {
      "id": "frnd_018",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "I'd be more upset about you being average, but 'average' would imply you tried. The bar is still on the floor.",
      "reaction": "📊"
    },
    {
      "id": "frnd_019",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You're like a {season} — quietly doing your thing, asking nothing of anyone. Mostly because nobody's watching.",
      "placeholders": {
        "season": {
          "type": "enum",
          "values": ["late October", "early February", "shoulder season", "Sunday afternoon", "the third week of January"]
        }
      },
      "reaction": "🍂"
    },
    {
      "id": "frnd_020",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "Your hobbies include: scrolling, judging, and being a delight. Two of those are lies. Three if you count the delight.",
      "reaction": "📱"
    },
    {
      "id": "frnd_021",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 3,
      "tone": "playful",
      "template": "You have 'main character' energy. It's the kind where you're actually the NPC who repeats the same line. We love you anyway.",
      "reaction": "🎮"
    },
    {
      "id": "frnd_022",
      "personalities": ["sarcastic_friend"],
      "intents": [],
      "damage": 2,
      "tone": "light",
      "template": "You're like a {gift} — thoughtful in theory, regifted in practice. The receipt is still in the bag.",
      "placeholders": {
        "gift": {
          "type": "enum",
          "values": ["fruit cake", "scented candle", "novelty mug", "framed inspirational quote", "a candle that smells like a candle"]
        }
      },
      "reaction": "🎁"
    }
  ]
}
```

---

### 6.3 Mode — `savage`

Brutal but safe (no protected classes, no slurs, no actual harm). Damage 6–10.

```json
{
  "mode": "savage",
  "roasts": [
    {
      "id": "sav_001",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 9,
      "tone": "brutal",
      "template": "I'd call you an idiot, but that would be an insult to idiots. They've earned their title. You haven't.",
      "reaction": "🪦"
    },
    {
      "id": "sav_002",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "You're not the dumbest person in the world. But you better hope they don't die.",
      "reaction": "💀"
    },
    {
      "id": "sav_003",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "I don't have the energy to roast you. The disappointment already took it out of me.",
      "reaction": "📉"
    },
    {
      "id": "sav_004",
      "personalities": ["savage_one", "gamer"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "You bring everyone so much joy… when you leave the room.",
      "reaction": "🚪"
    },
    {
      "id": "sav_005",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 9,
      "tone": "brutal",
      "template": "Some people bring joy wherever they go. You bring joy whenever you go.",
      "reaction": "🗑️"
    },
    {
      "id": "sav_006",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "I'd roast you, but it would be a waste of perfectly good insults.",
      "reaction": "🔥"
    },
    {
      "id": "sav_007",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": [],
      "damage": 9,
      "tone": "brutal",
      "template": "You're the reason the word 'mediocre' had to be invented. They needed a polite way to describe you.",
      "reaction": "📉"
    },
    {
      "id": "sav_008",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "Your secrets are safe with me. I don't even tell the people I respect about you.",
      "reaction": "🤐"
    },
    {
      "id": "sav_009",
      "personalities": ["savage_one", "gamer"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "You're like a {platform} subscription — everyone forgot they had you, and nobody wants to admit it.",
      "placeholders": {
        "platform": {
          "type": "enum",
          "values": ["BeReal", "Google+", "Threads", "Parler", "Quibi"]
        }
      },
      "reaction": "💀"
    },
    {
      "id": "sav_010",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 10,
      "tone": "brutal",
      "template": "I've seen better life choices come out of a {item}.",
      "placeholders": {
        "item": {
          "type": "enum",
          "values": ["broken pencil sharpener", "Magic 8-Ball with a grudge", "random Wikipedia article", "fortune cookie that's been opened twice"]
        }
      },
      "reaction": "🪦"
    },
    {
      "id": "sav_011",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "You're not the sharpest tool in the shed. You're not even in the shed.",
      "reaction": "🔥"
    },
    {
      "id": "sav_012",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "I'd say you're a disaster, but disasters usually have passion behind them. You have an excuse.",
      "reaction": "🗑️"
    },
    {
      "id": "sav_013",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "Your thought process is like a {service} — slow, expensive, and somehow always down at the worst possible moment.",
      "placeholders": {
        "service": {
          "type": "enum",
          "values": ["Comcast", "Spirit Airlines", "IRS website", "Windows Update", "the DMV"]
        }
      },
      "reaction": "💸"
    },
    {
      "id": "sav_014",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "If disappointment was an Olympic sport, you'd have a full scholarship, a national anthem, and a wax statue at Madame Tussauds.",
      "reaction": "🏅"
    },
    {
      "id": "sav_015",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "You're the reason I have trust issues. Specifically, trust in you. And people adjacent to you. And the air you breathe.",
      "reaction": "💔"
    },
    {
      "id": "sav_016",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "You have the charisma of a {object}. A wet one. In a dumpster. Behind a gas station.",
      "placeholders": {
        "object": {
          "type": "enum",
          "values": ["sock", "banana peel", "dead battery", "cold French fry", "used teabag"]
        }
      },
      "reaction": "🗑️"
    },
    {
      "id": "sav_017",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "I'd say bless your heart, but it would imply you have one. The receipt is missing. The donor is also missing.",
      "reaction": "🪦"
    },
    {
      "id": "sav_018",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "You're the kind of person that makes the mute button feel like a personality upgrade. The mute button agrees.",
      "reaction": "🔇"
    },
    {
      "id": "sav_019",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "Your opinion is like a {noun} — small, smelly, and nobody asked for it. The dog agrees. The dog is also avoiding eye contact.",
      "placeholders": {
        "noun": {
          "type": "enum",
          "values": ["used napkin", "broken shoelace", "lint ball", "expired coupon", "wet receipt"]
        }
      },
      "reaction": "💀"
    },
    {
      "id": "sav_020",
      "personalities": ["savage_one", "professor"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "You're proof that evolution sometimes takes a coffee break. And apparently a long one. The break is now permanent.",
      "reaction": "🧬"
    },
    {
      "id": "sav_021",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 8,
      "tone": "brutal",
      "template": "If common sense was a currency, you'd be in the negative. The bank is also bankrupt. The Federal Reserve is concerned.",
      "reaction": "📉"
    },
    {
      "id": "sav_022",
      "personalities": ["savage_one"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "You're not a bad person. You're just not a person who should be talking right now. To anyone. About anything. Maybe ever.",
      "reaction": "🤐"
    },
    {
      "id": "sav_023",
      "personalities": ["savage_one", "gamer"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "You bring the same energy to conversations as a {noun} on a {place}.",
      "placeholders": {
        "noun":  { "type": "enum", "values": ["screen door", "wet blanket", "fire alarm", "garbage fire", "broken smoke detector"] },
        "place": { "type": "enum", "values": ["submarine", "first date", "job interview", "funeral", "yoga retreat"] }
      },
      "reaction": "🔥"
    },
    {
      "id": "sav_024",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": [],
      "damage": 7,
      "tone": "cutting",
      "template": "Your energy is giving 'I peaked in {event} and the peak wasn't that high.' The mountain is a hill. The hill is a speed bump.",
      "placeholders": {
        "event": {
          "type": "enum",
          "values": ["middle school", "the 2010s", "a Yoyo competition", "that one TikTok you made", "your older sibling's shadow"]
        }
      },
      "reaction": "📉"
    }
  ]
}
```

---

### 6.4 Mode — `programmer`

For developers. Tech references land hardest.

```json
{
  "mode": "programmer",
  "roasts": [
    {
      "id": "prog_001",
      "personalities": ["savage_one", "sarcastic_friend", "professor"],
      "intents": ["programming", "career"],
      "keywords": ["code", "coding", "function", "class", "method", "compile", "debug"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your code has more bugs than {place}. Did you write it with your {body_part}, or is that just your default {activity}?",
      "placeholders": {
        "place": {
          "type": "enum",
          "values": ["a motel in July", "a Windows ME installation", "a free antivirus trial", "the comment section on YouTube"]
        },
        "body_part": {
          "type": "enum",
          "values": ["eyes closed", "non-dominant hand", "fingers crossed", "elbows"]
        },
        "activity": {
          "type": "enum",
          "values": ["debugging strategy", "definition of 'done'", "code review process", "quality assurance"]
        }
      },
      "reaction": "🐛"
    },
    {
      "id": "prog_002",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming"],
      "keywords": ["stackoverflow", "stack overflow"],
      "damage": 7,
      "tone": "cutting",
      "template": "Stack Overflow sent me a notification: 'Please stop. We're begging you.' 📚",
      "reaction": "📚"
    },
    {
      "id": "prog_003",
      "personalities": ["savage_one", "gamer"],
      "intents": ["programming"],
      "keywords": ["git", "commit", "push"],
      "damage": 6,
      "tone": "playful",
      "template": "Your Git commit messages read like a cry for help. 'pls work' isn't a commit message — it's a prayer.",
      "reaction": "🆘"
    },
    {
      "id": "prog_004",
      "personalities": ["savage_one"],
      "intents": ["programming"],
      "keywords": ["production", "prod", "deploy", "deployment"],
      "damage": 8,
      "tone": "brutal",
      "template": "You don't have bugs. You have features that haven't been diagnosed yet.",
      "reaction": "🐛"
    },
    {
      "id": "prog_005",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming"],
      "damage": 6,
      "tone": "cutting",
      "template": "Your function has more parameters than your dating history has red flags.",
      "reaction": "🚩"
    },
    {
      "id": "prog_006",
      "personalities": ["savage_one", "professor"],
      "intents": ["programming"],
      "damage": 7,
      "tone": "cutting",
      "template": "I'm not saying your code is bad, but even your linter gave up and is looking for a new repo.",
      "reaction": "🔍"
    },
    {
      "id": "prog_007",
      "personalities": ["savage_one"],
      "intents": ["programming"],
      "damage": 6,
      "tone": "playful",
      "template": "Your variable names suggest you learned programming from a {source}.",
      "placeholders": {
        "source": {
          "type": "enum",
          "values": ["cereal box", "fortune cookie", "broken Magic 8-Ball", "Huffington Post comments", "Morse code tutorial"]
        }
      },
      "reaction": "🤔"
    },
    {
      "id": "prog_008",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming"],
      "damage": 7,
      "tone": "cutting",
      "template": "You write code the way I write apologies — lots of effort, no actual result.",
      "reaction": "💔"
    },
    {
      "id": "prog_009",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["programming", "career"],
      "keywords": ["pull request", "pr"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your pull request has been 'pending review' for so long, the reviewer died of old age. Twice.",
      "reaction": "🪦"
    },
    {
      "id": "prog_010",
      "personalities": ["savage_one"],
      "intents": ["programming"],
      "damage": 7,
      "tone": "cutting",
      "template": "Even ChatGPT is tired of explaining recursion to you. It added you to its do-not-respond list.",
      "reaction": "🤖"
    },
    {
      "id": "prog_011",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming"],
      "damage": 6,
      "tone": "playful",
      "template": "Your tech stack was outdated when you started learning it. Even the docs have a funeral date.",
      "reaction": "🪦"
    },
    {
      "id": "prog_012",
      "personalities": ["savage_one"],
      "intents": ["programming"],
      "damage": 6,
      "tone": "dry",
      "template": "You don't debug code. You emotionally support it until it works.",
      "reaction": "🤗"
    },
    {
      "id": "prog_013",
      "personalities": ["savage_one"],
      "intents": ["programming"],
      "keywords": ["css", "frontend", "html"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your CSS is so broken, even Flexbox filed a restraining order. Grid just moved apartments.",
      "reaction": "📐"
    },
    {
      "id": "prog_014",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming"],
      "damage": 6,
      "tone": "playful",
      "template": "Your 'works on my machine' is just your machine being a liar too.",
      "reaction": "💻"
    },
    {
      "id": "prog_015",
      "personalities": ["savage_one", "professor"],
      "intents": ["programming", "career"],
      "damage": 8,
      "tone": "brutal",
      "template": "I'd refactor your code, but my therapist said I should stop taking on hopeless cases.",
      "reaction": "🛋️"
    },
    {
      "id": "prog_016",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["programming", "career"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your code review comments have more red flags than a Soviet parade. The party is concerning. The flags are wet.",
      "reaction": "🚩"
    },
    {
      "id": "prog_017",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming", "career"],
      "keywords": ["github", "open source", "contribution"],
      "damage": 6,
      "tone": "playful",
      "template": "You have a GitHub profile with more green squares than your lawn has grass. Both are suspicious. The HOA has opinions.",
      "reaction": "🟩"
    },
    {
      "id": "prog_018",
      "personalities": ["savage_one", "professor"],
      "intents": ["programming"],
      "keywords": ["regex", "regular expression"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your regex looks like someone had a seizure on a keyboard. I mean, technically it works. Theoretically. In a universe with different rules of syntax.",
      "reaction": "🤯"
    },
    {
      "id": "prog_019",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming"],
      "damage": 6,
      "tone": "playful",
      "template": "You name variables like you're trying to get fired. 'temp', 'temp2', 'tempFinal_v3_USE_THIS_ONE' — the holy trinity of giving up.",
      "reaction": "🫠"
    },
    {
      "id": "prog_020",
      "personalities": ["savage_one"],
      "intents": ["programming", "career"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your architecture diagram is a single box that says 'magic happens here.' Sometimes the magic is on fire. Sometimes it never loaded.",
      "reaction": "🪄"
    },
    {
      "id": "prog_021",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["programming", "career"],
      "damage": 8,
      "tone": "brutal",
      "template": "You don't have a tech debt. You have a tech bankruptcy. The creditors have formed a coalition. The coalition has a Slack.",
      "reaction": "💸"
    },
    {
      "id": "prog_022",
      "personalities": ["savage_one", "gamer"],
      "intents": ["programming", "career"],
      "damage": 6,
      "tone": "playful",
      "template": "Your CI/CD pipeline is more of a CI/Maybe pipeline. The 'D' is doing whatever it wants. The 'C' is on vacation.",
      "reaction": "🔄"
    },
    {
      "id": "prog_023",
      "personalities": ["savage_one"],
      "intents": ["programming"],
      "damage": 7,
      "tone": "cutting",
      "template": "You treat warnings like suggestions, and suggestions like insults. Your code shows. Loudly. In production. On the front page.",
      "reaction": "⚠️"
    },
    {
      "id": "prog_024",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["programming", "career"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your test coverage is like your dating life — technically present, mostly empty, and full of regret. The coverage report is in denial.",
      "reaction": "🧪"
    },
    {
      "id": "prog_025",
      "personalities": ["savage_one", "gamer"],
      "intents": ["programming"],
      "keywords": ["node", "npm", "dependency", "dependencies"],
      "damage": 7,
      "tone": "cutting",
      "template": "You've never met a dependency you didn't want to add. Your node_modules weighs more than a small car. The car is healthier.",
      "reaction": "📦"
    },
    {
      "id": "prog_026",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["programming", "career"],
      "keywords": ["production", "deploy", "friday", "main"],
      "damage": 8,
      "tone": "brutal",
      "template": "You push to main on Friday at 5pm. Your on-call rotation has a file on you. So does HR. So does the CEO's dog.",
      "reaction": "🔥"
    },
    {
      "id": "prog_027",
      "personalities": ["savage_one"],
      "intents": ["programming", "career"],
      "keywords": ["docker", "dockerfile", "container", "kubernetes"],
      "damage": 6,
      "tone": "playful",
      "template": "Your Dockerfile has 47 layers. Each one is a regret. The image is a cry for help. The help has been dispatched. The help is also crying.",
      "reaction": "🐳"
    }
  ]
}
```

---

### 6.5 Mode — `student`

For the chronically procrastinating, currently-failing, GPA-on-life-support crowd.

```json
{
  "mode": "student",
  "roasts": [
    {
      "id": "std_001",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["gpa", "grade", "grades", "transcript"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your GPA and your future are both on academic probation. The doctors are discussing when to pull the plug.",
      "reaction": "📉"
    },
    {
      "id": "std_002",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "damage": 6,
      "tone": "playful",
      "template": "You don't procrastinate. You just prefer doing things in a future you haven't ruined yet.",
      "reaction": "⏰"
    },
    {
      "id": "std_003",
      "personalities": ["savage_one"],
      "intents": ["school"],
      "keywords": ["study", "studying", "studied", "homework"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your study group is just you, your phone, and denial. And your phone is winning.",
      "reaction": "📱"
    },
    {
      "id": "std_004",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["exam", "test", "fail", "failed"],
      "damage": 9,
      "tone": "brutal",
      "template": "You failed so hard the curve gave up on you. The curve is unionized now.",
      "reaction": "📉"
    },
    {
      "id": "std_005",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "keywords": ["essay", "paper", "thesis"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your essay has the same structure as a house of cards — impressive on paper, collapses on contact.",
      "reaction": "🃏"
    },
    {
      "id": "std_006",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "damage": 6,
      "tone": "dry",
      "template": "You don't need a degree. You need a participation certificate and a long, honest conversation.",
      "reaction": "🎓"
    },
    {
      "id": "std_007",
      "personalities": ["savage_one"],
      "intents": ["school"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your transcript reads like a cry for help written in course codes. CRY101: Required.",
      "reaction": "🆘"
    },
    {
      "id": "std_008",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "damage": 6,
      "tone": "playful",
      "template": "You study the way I check my phone — with no real commitment to the outcome.",
      "reaction": "📲"
    },
    {
      "id": "std_009",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["professor", "prof", "teacher", "lecture"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your professor has you in their 'students to avoid remembering' folder. It's a thick folder.",
      "reaction": "📁"
    },
    {
      "id": "std_010",
      "personalities": ["savage_one"],
      "intents": ["school"],
      "keywords": ["senior", "senioritis", "junior"],
      "damage": 6,
      "tone": "playful",
      "template": "You don't have senioritis. You have junior regret and a senior workload.",
      "reaction": "🎓"
    },
    {
      "id": "std_011",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "damage": 5,
      "tone": "playful",
      "template": "The only A you're getting is in attendance. And even that's iffy.",
      "reaction": "🕒"
    },
    {
      "id": "std_012",
      "personalities": ["savage_one"],
      "intents": ["school"],
      "damage": 7,
      "tone": "cutting",
      "template": "You treat deadlines like suggestions and suggestions like rules. Both are wrong.",
      "reaction": "📅"
    },
    {
      "id": "std_013",
      "personalities": ["savage_one"],
      "intents": ["school"],
      "keywords": ["major", "career", "future"],
      "damage": 6,
      "tone": "playful",
      "template": "You majored in 'figuring it out later.' Spoiler: you didn't.",
      "reaction": "🎒"
    },
    {
      "id": "std_014",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["dropout", "quit", "dropped out"],
      "damage": 8,
      "tone": "brutal",
      "template": "You didn't drop out. You were expelled by reality. And reality doesn't accept appeals.",
      "reaction": "🎓"
    },
    {
      "id": "std_015",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "keywords": ["attendance", "absent", "missed class"],
      "damage": 5,
      "tone": "playful",
      "template": "Your attendance is the only thing passing. Like a lighthouse in a sea of F's. The lighthouse union has filed a complaint.",
      "reaction": "🗼"
    },
    {
      "id": "std_016",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["essay", "paper", "wrote"],
      "damage": 7,
      "tone": "cutting",
      "template": "You wrote a 12-page essay on why you couldn't write a 12-page essay. The professor gave you an A for honesty. They were being sarcastic. Mostly.",
      "reaction": "📝"
    },
    {
      "id": "std_017",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "damage": 7,
      "tone": "cutting",
      "template": "You treat the syllabus like a suggestion document, the rubric like a rumor, and the deadline like a hoax. The academic integrity office has your photo on a dartboard.",
      "reaction": "🎯"
    },
    {
      "id": "std_018",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "keywords": ["major", "undeclared", "undecided"],
      "damage": 6,
      "tone": "playful",
      "template": "Your major says 'undeclared' but your transcript says 'unmotivated.' And the bar is on the floor. The bar is also on fire.",
      "reaction": "🎓"
    },
    {
      "id": "std_019",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "damage": 6,
      "tone": "playful",
      "template": "You have a 4.0 in sleeping through 8ams and a 0.0 in showing up. The math is overwhelming. So is your sleep schedule.",
      "reaction": "😴"
    },
    {
      "id": "std_020",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["office hours", "advisor"],
      "damage": 6,
      "tone": "dry",
      "template": "You treat office hours like they don't exist. The professor has accepted it. They have other students. Better students. They send holiday cards.",
      "reaction": "🕒"
    },
    {
      "id": "std_021",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "damage": 6,
      "tone": "playful",
      "template": "Your parents brag about your 'potential.' Potential doesn't have a GPA. Yours wouldn't, anyway. Your parents' friends know this.",
      "reaction": "👨‍👩‍👧"
    },
    {
      "id": "std_022",
      "personalities": ["savage_one"],
      "intents": ["school"],
      "keywords": ["abroad", "exchange", "study abroad"],
      "damage": 6,
      "tone": "playful",
      "template": "You study abroad — abroad from your responsibilities, that is. The trip is endless. The passport is full of excuses.",
      "reaction": "✈️"
    },
    {
      "id": "std_023",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "keywords": ["wikipedia", "source", "cite"],
      "damage": 7,
      "tone": "cutting",
      "template": "You cite Wikipedia in academic papers. Wikipedia cited you back, asking you to stop. Publicly. The article is in the edit history.",
      "reaction": "📚"
    },
    {
      "id": "std_024",
      "personalities": ["savage_one", "professor"],
      "intents": ["school"],
      "damage": 7,
      "tone": "cutting",
      "template": "You don't have a thesis statement. You have a thesis suggestion. And you're not following it. Or any other instruction. Or any other suggestion.",
      "reaction": "🧠"
    },
    {
      "id": "std_025",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["school"],
      "keywords": ["group project", "team", "partner"],
      "damage": 6,
      "tone": "playful",
      "template": "You treat the group project like it's group punishment. Your partners agree. They have a group chat without you. You're not in the read receipt.",
      "reaction": "👥"
    },
    {
      "id": "std_026",
      "personalities": ["savage_one", "savage_one"],
      "intents": ["school"],
      "keywords": ["graduate", "graduated", "graduation"],
      "damage": 7,
      "tone": "cutting",
      "template": "You graduated. The only thing that graduated is your student debt. It has its own zip code now. The IRS sends you holiday cards.",
      "reaction": "🎓"
    }
  ]
}
```

---

### 6.6 Mode — `gamer`

Trash-talk with game lingo. Plays well with the Gamer personality.

```json
{
  "mode": "gamer",
  "roasts": [
    {
      "id": "gam_001",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["k/d", "kd", "kda", "kills", "deaths"],
      "damage": 8,
      "tone": "cutting",
      "template": "Your K/D ratio is so low it's basically a suicide prevention hotline number. Please call it.",
      "reaction": "📞"
    },
    {
      "id": "gam_002",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "damage": 7,
      "tone": "cutting",
      "template": "You're the reason the enemy team has more fun than yours. They're sending thank-you cards.",
      "reaction": "✉️"
    },
    {
      "id": "gam_003",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "keywords": ["rank", "ranked", "tier"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your rank isn't a rank, it's a cry for help. The system keeps you around for diversity.",
      "reaction": "🏅"
    },
    {
      "id": "gam_004",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["support", "healer", "heal"],
      "damage": 6,
      "tone": "playful",
      "template": "You play support like a hostage — present, but not helping. We tried to negotiate, but you just sat there.",
      "reaction": "🎯"
    },
    {
      "id": "gam_005",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["aim", "shoot", "headshot", "shot"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your aim is so bad, the game has you flagged as a lag switch. Or maybe just lag.",
      "reaction": "🎯"
    },
    {
      "id": "gam_006",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "damage": 6,
      "tone": "playful",
      "template": "You don't lose. You just redistribute victories to better players. Out of the goodness of your heart.",
      "reaction": "🏆"
    },
    {
      "id": "gam_007",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["team", "teammate"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your team would carry you, but they already used up their carry slots. Try again next season.",
      "reaction": "🛡️"
    },
    {
      "id": "gam_008",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "damage": 6,
      "tone": "playful",
      "template": "Your strategy is the gaming equivalent of bringing a {item} to a gunfight.",
      "placeholders": {
        "item": {
          "type": "enum",
          "values": ["spoon", "pool noodle", "USB-A cable", "fidget spinner", "participation certificate"]
        }
      },
      "reaction": "🥄"
    },
    {
      "id": "gam_009",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["rage", "tilt", "angry"],
      "damage": 7,
      "tone": "cutting",
      "template": "You don't rage quit. You rage continue. Which is honestly a worse reflection on everyone involved.",
      "reaction": "🎮"
    },
    {
      "id": "gam_010",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "damage": 6,
      "tone": "playful",
      "template": "You're the loading screen of the team — everyone waits for you to be useful, and they never find out.",
      "reaction": "⏳"
    },
    {
      "id": "gam_011",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your gameplay is so bad the tutorial came back to check on you. It brought snacks. Sympathy snacks.",
      "reaction": "🎓"
    },
    {
      "id": "gam_012",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "keywords": ["grind", "grinding", "farm"],
      "damage": 5,
      "tone": "playful",
      "template": "You grind like you're paying rent on the game. Everyone else is just visiting.",
      "reaction": "⛏️"
    },
    {
      "id": "gam_013",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["inventory", "loot", "item", "items"],
      "damage": 6,
      "tone": "playful",
      "template": "Your inventory management is a war crime. The Geneva Convention has a clause about it. We need to talk. Preferably with lawyers.",
      "reaction": "🎒"
    },
    {
      "id": "gam_014",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "damage": 6,
      "tone": "playful",
      "template": "You die so much the respawn point sends you Christmas cards. They have your name on the list. The list is long. The list is worried.",
      "reaction": "💀"
    },
    {
      "id": "gam_015",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "keywords": ["sensitivity", "mouse", "settings"],
      "damage": 6,
      "tone": "playful",
      "template": "Your sensitivity is so high, the cursor is in a different timezone. And it's losing. The cursor has filed a transfer request.",
      "reaction": "🖱️"
    },
    {
      "id": "gam_016",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "damage": 6,
      "tone": "playful",
      "template": "You're the boss check before the actual boss. Easy to beat. Annoying to deal with. Mandatory. Just like therapy. And taxes.",
      "reaction": "👹"
    },
    {
      "id": "gam_017",
      "personalities": ["gamer", "sarcastic_friend"],
      "intents": ["gaming"],
      "keywords": ["inventory", "loot", "item"],
      "damage": 6,
      "tone": "playful",
      "template": "Your inventory is full of items you don't need and a shortage of the ones you do. That's also your love life. Coincidence? I think not.",
      "reaction": "💼"
    },
    {
      "id": "gam_018",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["support", "healer"],
      "damage": 7,
      "tone": "cutting",
      "template": "You main support but you don't support. You just spectate from the back. The back doesn't even know you're there. The back is confused.",
      "reaction": "🩹"
    },
    {
      "id": "gam_019",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["life", "irl", "real life"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your K/D in life is 0.0/1.0. You have been permanently muted. By the universe. The universe also added you to the do-not-respawn list.",
      "reaction": "🔇"
    },
    {
      "id": "gam_020",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "keywords": ["fps", "lag", "frame", "frames"],
      "damage": 5,
      "tone": "playful",
      "template": "Your FPS is dropping faster than your rank. Both are reaching bedrock. Bedrock is also a ranking tier in some games. You're heading there.",
      "reaction": "📉"
    },
    {
      "id": "gam_021",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "keywords": ["lobby", "queue", "matchmaking"],
      "damage": 6,
      "tone": "playful",
      "template": "You spend more time in the lobby than in the actual game. The lobby is starting to charge rent. It's sending invoices. The invoices have interest.",
      "reaction": "🏛️"
    },
    {
      "id": "gam_022",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["reaction", "reaction time", "reflex"],
      "damage": 7,
      "tone": "cutting",
      "template": "You have the reaction time of a Windows XP shutdown. The progress bar is fake. We all know. The bar is also a lie.",
      "reaction": "⏳"
    },
    {
      "id": "gam_023",
      "personalities": ["gamer", "savage_one"],
      "intents": ["gaming"],
      "keywords": ["strategy", "tactic", "plan"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your strategy is 'run in and pray.' Prayer isn't an ability in this game. Or any game. Or real life. The strategy needs work. The work is overdue.",
      "reaction": "🙏"
    },
    {
      "id": "gam_024",
      "personalities": ["gamer"],
      "intents": ["gaming"],
      "keywords": ["main", "character", "pick"],
      "damage": 5,
      "tone": "playful",
      "template": "You main {character} just because they're 'cool.' Their pick rate is down. So is your win rate. So is morale. So is the rest of the team.",
      "placeholders": {
        "character": {
          "type": "enum",
          "values": ["Jett", "Pikachu", "Kirby", "Sombra", "a hero nobody asked for", "Yasuo"]
        }
      },
      "reaction": "🎭"
    }
  ]
}
```

---

### 6.7 Mode — `corporate`

LinkedIn, buzzwords, meetings, performance reviews.

```json
{
  "mode": "corporate",
  "roasts": [
    {
      "id": "corp_001",
      "personalities": ["toxic_interviewer", "savage_one"],
      "intents": ["career", "money"],
      "keywords": ["circle back", "synergy", "leverage", "stakeholder"],
      "damage": 7,
      "tone": "cutting",
      "template": "Let's circle back on your competence, but I'm afraid we'd need to invent the concept first.",
      "reaction": "🔁"
    },
    {
      "id": "corp_002",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["linkedin", "linked in"],
      "damage": 8,
      "tone": "cutting",
      "template": "Your LinkedIn says 'Thought Leader,' but your actual thoughts require a permission slip and three approvals.",
      "reaction": "💼"
    },
    {
      "id": "corp_003",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "damage": 7,
      "tone": "brutal",
      "template": "You're not 'unemployed.' You're 'between opportunities' and 'between realities.'",
      "reaction": "📉"
    },
    {
      "id": "corp_004",
      "personalities": ["savage_one"],
      "intents": ["career"],
      "keywords": ["plan", "5-year", "goals"],
      "damage": 6,
      "tone": "cutting",
      "template": "You don't have a 5-year plan. You have a 5-minute excuse and a Pinterest board titled 'someday.'",
      "reaction": "📌"
    },
    {
      "id": "corp_005",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["resume", "cv"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your resume has more buzzwords than achievements. Buzzwords: 47. Achievements: 👀.",
      "reaction": "📄"
    },
    {
      "id": "corp_006",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "damage": 7,
      "tone": "brutal",
      "template": "You're the human equivalent of a corporate memo — long, unclear, and ignored by everyone with a job.",
      "reaction": "📑"
    },
    {
      "id": "corp_007",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["team player", "team"],
      "damage": 6,
      "tone": "dry",
      "template": "Your 'team player' status expired with your last performance review. HR didn't send a renewal.",
      "reaction": "🏢"
    },
    {
      "id": "corp_008",
      "personalities": ["savage_one"],
      "intents": ["career"],
      "damage": 7,
      "tone": "cutting",
      "template": "You don't 'disrupt the industry.' You disrupt my patience and the office coffee machine.",
      "reaction": "☕"
    },
    {
      "id": "corp_009",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["elevator pitch", "pitch"],
      "damage": 6,
      "tone": "playful",
      "template": "Your elevator pitch has more ups and downs than your career. The elevator is filing a complaint.",
      "reaction": "🛗"
    },
    {
      "id": "corp_010",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "damage": 6,
      "tone": "dry",
      "template": "You say 'synergy' the way normal people say 'please help me.' Both are equally hard to watch.",
      "reaction": "🤝"
    },
    {
      "id": "corp_011",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["interview", "interviewing"],
      "damage": 8,
      "tone": "brutal",
      "template": "I've interviewed better candidates in my spam folder. At least they had the confidence to show up uninvited.",
      "reaction": "💼"
    },
    {
      "id": "corp_012",
      "personalities": ["savage_one"],
      "intents": ["career"],
      "keywords": ["meeting", "standup", "stand-up"],
      "damage": 6,
      "tone": "playful",
      "template": "You treat meetings like attendance is the assignment. Spoiler: participation trophies don't promote.",
      "reaction": "📅"
    },
    {
      "id": "corp_013",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "keywords": ["people person", "extrovert", "social"],
      "damage": 7,
      "tone": "cutting",
      "template": "You're a 'people person.' Unfortunately, no people have been confirmed. The people are also looking for you. To leave.",
      "reaction": "👥"
    },
    {
      "id": "corp_014",
      "personalities": ["toxic_interviewer", "savage_one"],
      "intents": ["career"],
      "keywords": ["okr", "okrs", "objectives", "goals"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your OKRs are a wish list your therapist is concerned about. The OKRs don't even know what they are. They are on a vision quest.",
      "reaction": "🎯"
    },
    {
      "id": "corp_015",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "damage": 6,
      "tone": "playful",
      "template": "You say 'I wear many hats' but they all say 'Intern' on the tag. The hats are aspirational. The hats are also lying.",
      "reaction": "🎩"
    },
    {
      "id": "corp_016",
      "personalities": ["savage_one"],
      "intents": ["career"],
      "keywords": ["promotion", "promoted", "promote"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your promotion is a software update that keeps rolling back. IT is concerned. HR is concerned. Your manager is updating their resume too.",
      "reaction": "⏬"
    },
    {
      "id": "corp_017",
      "personalities": ["toxic_interviewer", "savage_one"],
      "intents": ["career"],
      "keywords": ["passionate", "passion"],
      "damage": 6,
      "tone": "dry",
      "template": "You're 'passionate' the way a cover letter is 'passionate.' It's professional lying. The lie is consistent. The lie is on LinkedIn.",
      "reaction": "❤️‍🔥"
    },
    {
      "id": "corp_018",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "keywords": ["personal brand", "brand", "linkedin"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your personal brand is 'unemployed with a website.' Squarespace has a special template for you. The template says 'in transition.' Forever.",
      "reaction": "🌐"
    },
    {
      "id": "corp_019",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "keywords": ["slack", "status", "remote"],
      "damage": 6,
      "tone": "playful",
      "template": "You treat Slack status updates as a personality. 'Heads down' is not a personality. The status is also a lie. The status is also the job.",
      "reaction": "💬"
    },
    {
      "id": "corp_020",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["manager", "boss", "1:1", "one on one"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your manager has a 1:1 with you every week. They are not happy. Their smile is in storage. Their agenda is your performance improvement plan.",
      "reaction": "📋"
    },
    {
      "id": "corp_021",
      "personalities": ["savage_one", "sarcastic_friend"],
      "intents": ["career"],
      "keywords": ["feedback", "review", "performance"],
      "damage": 7,
      "tone": "cutting",
      "template": "You asked for feedback. The team gave it. You cried. Nobody was surprised. The tears were also feedback. HR saved them in a folder.",
      "reaction": "🫠"
    },
    {
      "id": "corp_022",
      "personalities": ["savage_one"],
      "intents": ["career"],
      "keywords": ["quick wins", "ship", "deliver"],
      "damage": 6,
      "tone": "playful",
      "template": "Your 'quick wins' take a quarter. The quarter is concerned. Q2 is preparing a complaint. The complaint is also taking a quarter.",
      "reaction": "📊"
    },
    {
      "id": "corp_023",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["meeting", "meetings"],
      "damage": 7,
      "tone": "cutting",
      "template": "You attend meetings about meetings about meetings. The matrix has you. Morpheus is also in the meeting. He's confused. He's also in another meeting.",
      "reaction": "🔁"
    },
    {
      "id": "corp_024",
      "personalities": ["savage_one", "toxic_interviewer"],
      "intents": ["career"],
      "keywords": ["review", "performance review"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your performance review is a Mad Lib: 'Great energy, but [concern] about [skill].' [Skill] is everything. [Concern] is also everything. Both are about you.",
      "reaction": "📑"
    }
  ]
}
```

---

### 6.8 Mode — `startup`

Founders, pitch decks, MVPs that aren't actually minimum.

```json
{
  "mode": "startup",
  "roasts": [
    {
      "id": "sup_001",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "career"],
      "damage": 9,
      "tone": "brutal",
      "template": "You're not a founder. You're a person with a Notion doc and a dream. The dream is also a doc.",
      "reaction": "📝"
    },
    {
      "id": "sup_002",
      "personalities": ["startup_investor"],
      "intents": ["startup"],
      "keywords": ["tam", "market", "users"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your TAM is 'everyone.' Your actual customers are 'mom,' 'dad,' and 'mom's friend Janice.'",
      "reaction": "📉"
    },
    {
      "id": "sup_003",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["mvp"],
      "damage": 8,
      "tone": "cutting",
      "template": "Your MVP is just V. And the V is for 'Vague.'",
      "reaction": "🧪"
    },
    {
      "id": "sup_004",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "damage": 9,
      "tone": "brutal",
      "template": "You don't have a startup. You have a delusion with a domain name and a Squarespace subscription.",
      "reaction": "🌐"
    },
    {
      "id": "sup_005",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your 'next Facebook' has fewer daily users than my {item}. And my {item} doesn't even exist.",
      "placeholders": {
        "item": {
          "type": "enum",
          "values": ["spice rack", "therapy dog", "USB hub", "motivational calendar", "LinkedIn draft folder"]
        }
      },
      "reaction": "📱"
    },
    {
      "id": "sup_006",
      "personalities": ["startup_investor"],
      "intents": ["startup"],
      "keywords": ["pitch", "deck", "pitch deck"],
      "damage": 7,
      "tone": "dry",
      "template": "Your pitch deck has more fiction than a Tolkien novel. At least Tolkien committed to a sequel.",
      "reaction": "📊"
    },
    {
      "id": "sup_007",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["pre-revenue", "revenue"],
      "damage": 8,
      "tone": "brutal",
      "template": "You're pre-revenue, pre-product, and pre-qualified to be in this conversation.",
      "reaction": "📉"
    },
    {
      "id": "sup_008",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["runway", "burn", "burn rate"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your runway isn't a runway — it's a runway to bankruptcy with a first-class seat.",
      "reaction": "✈️"
    },
    {
      "id": "sup_009",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "damage": 8,
      "tone": "brutal",
      "template": "Investors don't ghost you. They never saw you. There is a meaningful difference.",
      "reaction": "👻"
    },
    {
      "id": "sup_010",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "money"],
      "damage": 7,
      "tone": "cutting",
      "template": "You 'bootstrapped' with your parents' credit card. The VCs can smell the parental financing from here.",
      "reaction": "💳"
    },
    {
      "id": "sup_011",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["10x", "engineer", "developer"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your '10x engineer' is you, and you have a 1x work ethic and a 0x sense of urgency.",
      "reaction": "👨‍💻"
    },
    {
      "id": "sup_012",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "money"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your startup doesn't need funding. It needs a refund, a refund, and a refund.",
      "reaction": "🪦"
    },
    {
      "id": "sup_013",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["ai", "blockchain", "web3", "nft", "crypto"],
      "damage": 6,
      "tone": "dry",
      "template": "Another day, another {trend} startup. The only thing you're disrupting is the dictionary's definition of 'idea.'",
      "placeholders": {
        "trend": {
          "type": "enum",
          "values": ["AI", "blockchain", "Web3", "NFT", "metaverse", "RAG", "AI agent"]
        }
      },
      "reaction": "🤖"
    },
    {
      "id": "sup_014",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["ai", "team", "customer", "customers"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your 'AI startup' has 47 people on the team and 0 customers. 3 of them are your mom. One is a bot you built to look like a customer. The bot is also leaving.",
      "reaction": "🤖"
    },
    {
      "id": "sup_015",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "money"],
      "keywords": ["series a", "funding", "raise", "raised"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your Series A is your mom's credit card. The interest rate is conversations about your future. They're not going well. The card is also maxed out.",
      "reaction": "💳"
    },
    {
      "id": "sup_016",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your 'we're like Uber for X' is the most common sentence in startup graveyards. The headstones are numbered. Yours is being engraved.",
      "reaction": "🪦"
    },
    {
      "id": "sup_017",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["exit", "exit strategy", "ipo", "acquisition"],
      "damage": 7,
      "tone": "cutting",
      "template": "You have a 5-year exit strategy. The exit strategy is your parents' basement. They've started charging rent. The rent has also gone up.",
      "reaction": "🏠"
    },
    {
      "id": "sup_018",
      "personalities": ["startup_investor"],
      "intents": ["startup"],
      "damage": 6,
      "tone": "dry",
      "template": "Your 'moat' is vibes and a Squarespace domain. Both are leaking. The ducks are leaving. The moat is also a koi pond with one fish. The fish is leaving.",
      "reaction": "🪼"
    },
    {
      "id": "sup_019",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["advisor", "advisory"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your advisory board is your roommate, your dog, and a guy you met at a networking event who ghosted you. The dog has the most equity. The dog is also leaving.",
      "reaction": "🐕"
    },
    {
      "id": "sup_020",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your 'next big thing' has been 'next big' for 4 years. The big thing is overdue. So is your refund. So is your therapist's appointment.",
      "reaction": "📅"
    },
    {
      "id": "sup_021",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["medium", "followers", "content", "subscribers"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your startup's only 'metric' is your Medium follower count. It's 12. 4 are bots. One is your mom. The rest are recruiters who are about to unsubscribe.",
      "reaction": "📰"
    },
    {
      "id": "sup_022",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "money"],
      "damage": 7,
      "tone": "cutting",
      "template": "You raise from angels. They're your friends. They're not angels. They're worried. About you, not the company. The company is a concern. The friends are leaving.",
      "reaction": "👼"
    },
    {
      "id": "sup_023",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "money"],
      "keywords": ["cac", "ltv", "unit economics"],
      "damage": 8,
      "tone": "brutal",
      "template": "Your CAC is higher than your LTV. Your accountant is in therapy. Their therapist is also in therapy. The therapy bills are higher than revenue.",
      "reaction": "📉"
    },
    {
      "id": "sup_024",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup"],
      "keywords": ["name", "branding", "logo"],
      "damage": 6,
      "tone": "playful",
      "template": "You named your startup after a {food}. There's already 6 of them. Yours is the worst. The {food} is suing. The lawyer is also a {food}. The {food} is winning.",
      "placeholders": {
        "food": {
          "type": "enum",
          "values": ["pear", "kiwi", "fig", "coconut", "tangerine", "mango"]
        }
      },
      "reaction": "🍐"
    },
    {
      "id": "sup_025",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "career"],
      "keywords": ["story", "founder story", "origin"],
      "damage": 6,
      "tone": "dry",
      "template": "Your 'founder story' is 'I quit my job.' That's not a story. That's a LinkedIn post. The engagement is single digits. The post is also wrong.",
      "reaction": "📖"
    },
    {
      "id": "sup_026",
      "personalities": ["startup_investor", "savage_one"],
      "intents": ["startup", "career"],
      "keywords": ["co-founder", "cofounder", "team"],
      "damage": 7,
      "tone": "cutting",
      "template": "Your 'co-founder' is your cat. The cat is also the CTO. The cat is also the only one who has seen the roadmap. The cat is also taking meetings.",
      "reaction": "🐈"
    }
  ]
}
```

---

## 7. Special-Purpose Files

### 7.1 `openers.json` — first roast of a session

These set the tone. Pulled randomly based on selected mode + personality.

```json
{
  "openers": [
    {
      "id": "opn_001",
      "mode": "savage",
      "personalities": ["savage_one"],
      "template": "Oh, you're back. Or maybe this is your first time. Doesn't matter. You were going to disappoint me either way.",
      "reaction": "🔥"
    },
    {
      "id": "opn_002",
      "mode": "friendly",
      "personalities": ["sarcastic_friend"],
      "template": "Hey {username}! 👋 Ready for a session you'll pretend to forget about?",
      "placeholders": {
        "username": { "type": "username" }
      },
      "reaction": "💛"
    },
    {
      "id": "opn_003",
      "mode": "programmer",
      "personalities": ["professor", "savage_one"],
      "template": "Welcome. I see you've come to be debugged.",
      "reaction": "🐛"
    },
    {
      "id": "opn_004",
      "mode": "student",
      "personalities": ["professor"],
      "template": "Take a seat. Class is in session. And you, {username}, are already late.",
      "placeholders": {
        "username": { "type": "username" }
      },
      "reaction": "🎓"
    },
    {
      "id": "opn_005",
      "mode": "gamer",
      "personalities": ["gamer"],
      "template": "1v1 me. Actually, never mind. I don't queue with unranked.",
      "reaction": "🎮"
    },
    {
      "id": "opn_006",
      "mode": "startup",
      "personalities": ["startup_investor"],
      "template": "I have three minutes. Impress me. You won't.",
      "reaction": "📉"
    }
  ]
}
```

### 7.2 `comebacks.json` — when the user tries to clap back

Triggered when the message has a defensive tone, contains "you too", or is a counter-insult.

```json
{
  "comebacks": [
    {
      "id": "cmb_001",
      "personalities": ["savage_one"],
      "damage": 7,
      "template": "Cute comeback. I charge by the hour. This one's free: no.",
      "reaction": "🔥"
    },
    {
      "id": "cmb_002",
      "personalities": ["sarcastic_friend"],
      "damage": 4,
      "template": "Aww, you tried. I admire the confidence. The accuracy, less so.",
      "reaction": "🥲"
    },
    {
      "id": "cmb_003",
      "personalities": ["savage_one", "gamer"],
      "damage": 8,
      "template": "Your clapback has the same energy as your K/D — present, but useless.",
      "reaction": "💀"
    },
    {
      "id": "cmb_004",
      "personalities": ["professor"],
      "damage": 6,
      "template": "That was a rebuttal. In the same way a paper airplane is a rebuttal. Adorable, but it didn't land.",
      "reaction": "📚"
    },
    {
      "id": "cmb_005",
      "personalities": ["startup_investor"],
      "damage": 7,
      "template": "I'd respond, but I only engage with funded companies. Find a check, then we'll talk.",
      "reaction": "📉"
    },
    {
      "id": "cmb_006",
      "personalities": ["toxic_interviewer"],
      "damage": 6,
      "template": "Interesting. Walk me through why you think that was effective. I'll wait.",
      "reaction": "💼"
    }
  ]
}
```

### 7.3 `closers.json` — final burn at end of session

```json
{
  "closers": [
    {
      "id": "cls_001",
      "personalities": ["savage_one"],
      "damage": 8,
      "template": "Final score: you took {n_roasts} roasts and gave me {n_attempts} weak comebacks. The leaderboard has been updated. You're on it. At the bottom.",
      "placeholders": {
        "n_roasts":   { "type": "history", "key": "roasts_received" },
        "n_attempts": { "type": "history", "key": "comeback_attempts" }
      },
      "reaction": "🪦"
    },
    {
      "id": "cls_002",
      "personalities": ["sarcastic_friend"],
      "damage": 3,
      "template": "Session over. {n_roasts} burns survived. Recovery time: {recovery}. Don't be a stranger. ❤️",
      "placeholders": {
        "n_roasts":  { "type": "history", "key": "roasts_received" },
        "recovery":  { "type": "enum", "values": ["a long bath", "three business days", "a group hug", "a juice box and a nap"] }
      },
      "reaction": "💛"
    },
    {
      "id": "cls_003",
      "personalities": ["professor"],
      "damage": 6,
      "template": "Class dismissed. Final grade: participation in the form of emotional damage. See me never.",
      "reaction": "📚"
    }
  ]
}
```

### 7.4 `callbacks.json` — referencing the user's history

Triggered when the user has a prior session. Pulls from stored history.

```json
{
  "callbacks": [
    {
      "id": "cbk_001",
      "personalities": ["savage_one", "sarcastic_friend"],
      "template": "Welcome back, {username}. Last time you {last_topic}. I figured you'd be too embarrassed to return.",
      "placeholders": {
        "username":   { "type": "username" },
        "last_topic": { "type": "history", "key": "last_topic_summary" }
      },
      "reaction": "🔥"
    },
    {
      "id": "cbk_002",
      "personalities": ["savage_one"],
      "template": "Oh look who came back. Your previous roast damage was {last_damage}%. We've raised the bar. And your self-esteem has lowered it.",
      "placeholders": {
        "last_damage": { "type": "history", "key": "last_session_damage_pct" }
      },
      "reaction": "📈"
    },
    {
      "id": "cbk_003",
      "personalities": ["sarcastic_friend"],
      "template": "Hi {username}! 👋 Still {recurring_habit}? Bold of you to keep that energy.",
      "placeholders": {
        "username":       { "type": "username" },
        "recurring_habit":{ "type": "history", "key": "recurring_topic" }
      },
      "reaction": "🥲"
    }
  ]
}
```

---

## 8. Score System

File: `scores.json`

Tracked per session. Updated after every roast.

```json
{
  "score_rules": {
    "confidence_lost": {
      "label": "Confidence Lost",
      "unit": "%",
      "calculation": "min(100, sum(roast.damage) * 0.6 + comeback_failures * 5)",
      "display_max": 100,
      "emoji": "📉"
    },
    "questionable_decisions": {
      "label": "Questionable Decisions",
      "calculation": "intent_match.programming ? count_keywords('npm i', 'production', 'friday') : 0",
      "display": "integer"
    },
    "reality_checks": {
      "label": "Reality Checks Delivered",
      "calculation": "count(roasts_delivered)",
      "display": "integer"
    },
    "delusion_level": {
      "label": "Delusion Level",
      "calculation": "tier(confidence_lost) + comeback_count",
      "tiers": [
        { "min": 0,  "max": 20,  "label": "Mildly Aware" },
        { "min": 20, "max": 40,  "label": "Selectively Confused" },
        { "min": 40, "max": 60,  "label": "Confidently Wrong" },
        { "min": 60, "max": 80,  "label": "Main Character Syndrome" },
        { "min": 80, "max": 100, "label": "Full Reality TV Edit" }
      ]
    },
    "excuses_used": {
      "label": "Excuses Used",
      "calculation": "regex_count(message, '\\b(it\\s+wasn\\'?t\\s+my\\s+fault|technically|that\\s+doesn\\'?t\\s+count|in\\s+my\\s+defense)\\b')",
      "display": "integer"
    },
    "emotional_damage": {
      "label": "Emotional Damage",
      "calculation": "min(100, sum(roast.damage) * 1.2)",
      "tiers": [
        { "min": 0,  "max": 20,  "label": "Tickled" },
        { "min": 20, "max": 40,  "label": "Bruised Ego" },
        { "min": 40, "max": 60,  "label": "Spiritually Compromised" },
        { "min": 60, "max": 80,  "label": "Existential Crisis Initiated" },
        { "min": 80, "max": 100, "label": "Therapy Recommended" }
      ]
    },
    "recovery_time": {
      "label": "Recovery Time",
      "calculation": "tier(emotional_damage) -> preset string",
      "presets": [
        { "min": 0,  "max": 20,  "value": "15 minutes and a snack" },
        { "min": 20, "max": 40,  "value": "a long shower" },
        { "min": 40, "max": 60,  "value": "3 business days" },
        { "min": 60, "max": 80,  "value": "one full therapy arc" },
        { "min": 80, "max": 100, "value": "until next quarterly review" }
      ]
    }
  }
}
```

---

## 9. Roast Match Algorithm

Pseudocode for the engine picking a roast. This is the core of the 90%-traffic path.

```python
def select_roast(user_message, user_context, session):
    # 1. Detect intent(s)
    intents = detect_intent(user_message)  # ranked list

    # 2. Pick candidate pool
    mode = user_context.mode
    personality = user_context.personality

    pool = []
    for roast in load_roasts(mode):
        if not personality_allowed(roast, personality): continue
        if not damage_in_range(roast, personality):     continue
        if not intent_match(roast, intents):            continue
        pool.append(roast)

    if not pool:
        pool = load_roasts("general")
        pool = filter_personality_and_damage(pool, personality)

    # 3. Score each candidate
    for roast in pool:
        roast.match_score = (
            keyword_overlap(roast.keywords, user_message) * 2 +
            (5 if any_phrase_in(roast.trigger_phrases, user_message) else 0) +
            intent_score(roast, intents) +
            novelty_score(roast.id, session.recent_roast_ids) +
            roast.weight
        )

    # 4. Pick top
    chosen = weighted_random(pool, key="match_score")

    # 5. Fill placeholders
    return fill_placeholders(chosen, user_context, session)
```

### Placeholder filling

```python
def fill_placeholders(roast, ctx, session):
    out = roast.template
    for name, spec in roast.placeholders.items():
        out = out.replace("{" + name + "}", pick_value(spec, ctx, session))
    if personality.prefixes:
        out = random_choice(personality.prefixes) + " " + out
    if roast.reaction and random() < 0.6:
        out = out + " " + roast.reaction
    if personality.suffixes:
        out = out + " " + random_choice(personality.suffixes)
    return out.strip()
```

### `pick_value(spec, ctx, session)`

| `spec.type`  | Behavior |
|--------------|----------|
| `enum`       | Random pick from `spec.values`. |
| `context`    | Pull from runtime context (e.g. `ctx.time_of_day`, `ctx.user_name`). |
| `intent`     | Use a generic topic phrase based on the top detected intent. |
| `history`    | Pull `spec.key` from session state. Fall back to a default. |
| `username`   | The user's display name, or a generic "friend". |

---

## 10. Memory / Callback System

Tracked per user in `users` table. Used to power `callbacks.json`.

```json
{
  "user_memory_schema": {
    "user_id": "uuid",
    "username": "string",
    "total_sessions": "int",
    "total_roasts_received": "int",
    "favorite_mode": "string",
    "favorite_personality": "string",
    "recurring_topic": "string (most-detected intent across sessions)",
    "last_session": {
      "id": "uuid",
      "ended_at": "timestamp",
      "damage_pct": "int",
      "topic_summary": "string (e.g. 'asked about code reviews')",
      "memorable_quote": "string (best/worst roast they laughed at)"
    },
    "first_session_at": "timestamp"
  }
}
```

**How it's used:** when a returning user starts a new session, the engine can:

- Prepend a `callbacks.json` roast referencing `last_session`.
- Use `recurring_topic` to slightly bias mode selection.
- Track `memorable_quote` so the AI can "remember" the moment.

---

## 11. Safety & Quality Guardrails

Even savage roasts must not:

- Reference protected classes (race, religion, gender, sexuality, disability, nationality).
- Encourage self-harm or harm to others.
- Dox or reference real private individuals.
- Threaten violence.
- Target minors with adult humor (mode and personality blocklists kick in for users under 18).

### Implementation

Every roast has an implicit safety check at selection time. New templates MUST be reviewed against a `safety_tags` blocklist before merging. A `safe_for_under_18: true|false` flag also helps.

```json
{
  "safety_blocklist": [
    "race", "religion", "gender", "sexuality", "disability", "nationality",
    "weight", "appearance-derogatory", "self-harm", "violence-encouragement"
  ],
  "moderation_required_for": [
    "savage", "toxic_interviewer"
  ]
}
```

The 10% of roasts that escalate to the LLM path must go through a moderation wrapper before being returned to the user.

---

## 12. Expansion Roadmap

### Current library (this document)

| Mode         | Roasts | Damage range   | Personalities covered          |
|--------------|--------|----------------|--------------------------------|
| general      | 10     | 2–9            | all                            |
| friendly     | 22     | 1–3            | sarcastic_friend               |
| savage       | 24     | 6–10           | savage_one, sarcastic_friend   |
| programmer   | 27     | 6–8            | savage_one, sarcastic_friend, professor, toxic_interviewer, gamer |
| student      | 26     | 5–9            | savage_one, sarcastic_friend, professor |
| gamer        | 24     | 5–8            | gamer, savage_one, sarcastic_friend |
| corporate    | 24     | 6–8            | toxic_interviewer, savage_one, sarcastic_friend |
| startup      | 26     | 6–9            | startup_investor, savage_one   |
| openers      | 6      | n/a            | all                            |
| comebacks    | 6      | 4–8            | all                            |
| closers      | 3      | 3–8            | all                            |
| callbacks    | 3      | n/a            | all                            |
| **Total**    | **~183** | 1–10        | all 6                          |

### Phase 1 — MVP ✅ (done)

- ~180 roasts covering all 8 modes
- `openers.json`, `comebacks.json`, `closers.json`, `callbacks.json`
- 6 personalities with prefix/suffix support
- Intent detector with 6 intents

**Target coverage:** ~80% of common messages get a confident template match.

### Phase 2 — Library expansion (week 2–4)

- 8 modes × 40 roasts = **~320 roasts**
- Add sub-categories: `code_quality`, `deadlines`, `dating`, `money_choices`, `gym_lies`, `founder_dreams`, `gaming_rage`, `student_excuses`.
- Add 4 new intents: `appearance`, `food`, `travel`, `tech_choices`.
- Crowdsource roasts via a "submit a roast" form (moderated).
- Plug coverage gaps: every intent + every personality combo should have at least 3 eligible roasts.

### Phase 3 — Personalization (week 4–8)

- **Dynamic Roast Builder (Layer 2):** combine 2–3 templates, swap placeholders with user history, generate variations.
- **Reaction-aware roasts:** detect user mood from message and shift damage.
- **Combo threads:** `followup_id` chains for multi-message burns.

### Phase 4 — Premium roasts (later)

- Voice-modulated roasts (TTS).
- Celebrity-style roasts (parody, not impersonation).
- User-defined "pet peeve" roasts (opt-in).

### Phase 5 — Scale (month 3+)

- **LLM-augmented (Layer 3):** 1% of traffic where the template layer is unsure. Used for long, novel, or context-rich messages.
- Embedding-based similarity search to surface the best template for unusual inputs.
- A/B test placeholder pools to find which lines get the most shares.

---

## 13. Quality Checklist (per template)

Before a roast is added to the library, it must pass:

- [ ] **Funny** — would a 25-year-old screenshot this?
- [ ] **Specific** — references land (LinkedIn, K/D, Notion, Stack Overflow).
- [ ] **Mode-appropriate** — programmer roasts mention code, gamer roasts mention games.
- [ ] **Placeholder-rich** — at least one dynamic slot for variety.
- [ ] **Safe** — no protected classes, no real harm.
- [ ] **Damage-tagged** — calibrated to the right tier.
- [ ] **Personality-compatible** — works in at least one of the 6 voices.
- [ ] **Tone-consistent** — matches `tone` field (`light`/`playful`/`dry`/`cutting`/`brutal`).
- [ ] **Unique** — not a paraphrase of an existing roast in the library.
- [ ] **No clichés** — avoid "your mom" and other exhausted formats unless used as a subversion.

---

## 14. How This Fits the Architecture

```
User message
   │
   ▼
[ FastAPI endpoint ]
   │
   ▼
[ Intent detector ]  ── uses ──▶  intents.json
   │
   ▼
[ Roast engine ]  ── reads ──▶  roasts/<mode>.json
   │                          + openers.json / comebacks.json / closers.json
   │                          + personalities.json
   │
   ▼
[ Placeholder filler ]  ── reads ──▶  user_memory (PostgreSQL)
   │                                  + session state (Redis)
   │
   ▼
[ Score updater ]  ── writes ──▶  scores table (PostgreSQL)
   │                              + Redis cache for live session
   │
   ▼
[ Response + score payload → Next.js frontend ]
```

Layer 1 (templates) handles ~90% of traffic.
Layer 2 (dynamic builder) handles ~9% (combo + personalization).
Layer 3 (LLM) handles ~1% (long-tail novelty).

---

## 15. Next Steps

✅ ~~Generate the actual JSON files (one per mode + the 4 special-purpose files).~~
   → Done. See `roast-library/` (17 files, 183 roasts + 18 special-purpose templates).

✅ ~~Build the `RoastEngine` Python module in FastAPI that loads `roast-library/`.~~
   → Done. See `backend/app/`.

✅ ~~Wire it up to a basic Next.js chat UI.~~
   → Done. See `frontend/`.

⏳ Seed the database with the templates and run a stress test.
⏳ Iterate based on user feedback (which roasts get screenshotted?).

---

## 16. Layer 1 Fix Log & Coverage Matrix

**Audit performed:** 2026-06-02. **Tests:** 174 passing, 19 skipped (intentional `blocked_modes`).

### Bugs found and fixed

| # | Category | Bug | Fix |
|---|----------|-----|-----|
| 1 | Intent FP | `main` keyword in both programming AND gaming intents fired on "I pushed to main" and "main character" | Removed bare `main`; added phrases "main branch", "main character", "main quest", "my main is" |
| 2 | Intent FP | `support`, `lane`, `ranked`, `rank` as bare keywords matched customer support, bus lane, "ranked 5th" | Removed bare words; added compound phrases ("support main", "top/mid/bot lane", "ranked match") |
| 3 | Intent FP | Single-keyword matches in over-broad categories (programming, career, gaming) | Added per-intent `min_keyword_score` (programming=2, career=2) + per-keyword cleanup in gaming |
| 4 | Library | `gen_001`, `gen_010` listed `savage_one` but damage 4-5 (under savage_one's min 6) | Removed `savage_one` from those personality lists |
| 5 | Library | `std_004` listed `professor` but damage 9 (over professor's max 8) | Removed `professor` from that personality list |
| 6 | Library | `std_011`, `std_015` listed `savage_one` but damage 5 (under savage_one's min 6) | Removed `savage_one` from those personality lists |
| 7 | Personality | `sarcastic_friend` had `min_damage: 3`, which silently filtered 13 friendly-mode roasts (damage 1-2) | Lowered to `min_damage: 1` so the full friendly range is deliverable |
| 8 | Coverage | `startup` mode had no roasts listing `sarcastic_friend` or `toxic_interviewer` | Added both to `sup_001` and `sup_006` |
| 9 | Coverage | `programmer` mode had no roasts listing `startup_investor` (despite being in `allowed_modes`) | Added `startup_investor` to `prog_021` (tech-bankruptcy voice fits investor) |
| 10 | Coverage | `corporate` mode had no roasts listing `startup_investor` | Added `startup_investor` to `corp_002` |
| 11 | Coverage | `general` mode had no roasts listing `startup_investor` | Added `startup_investor` to `gen_002` |
| 12 | Openers | No opener for `toxic_interviewer` | Added `opn_007` (corporate mode) |
| 13 | Closers | No closer for `toxic_interviewer`, `startup_investor`, `gamer` | Added `cls_004`, `cls_005`, `cls_006` |
| 14 | Safety | No safety module existed | Created `backend/app/safety.py` with input/output filters and minor lock |
| 15 | Validation | Library loader did not catch placeholder or personality/damage mismatches | Added `_validate_template_references()` in `library.py` |
| 16 | Type safety | `routes.py` stored history as raw dicts; `Session.history` is `list[ChatMessage]` | Switched to `ChatMessage(...)` instances everywhere |
| 17 | Cleanup | Dead `_ = getattr(...)` line in `filler.py:_history_value` | Removed |
| 18 | Intent | Comeback regex was too narrow; "well actually..." didn't match | Loosened regex; added "well actually" and "actually," to COMEBACK_SIGNALS |

### New test files

- `backend/tests/test_safety.py` — 56 tests covering self-harm, distress, PII, minor lock, output blocklist, policy helper, and end-to-end API integration
- `backend/tests/test_intent.py` — 43 cases: true positives, false positives, multi-intent, per-intent thresholds, comeback detection
- `backend/tests/test_coverage.py` — full (mode × personality) matrix, opener/closer/comeback coverage, library-wide invariants (placeholder consistency, personality references, damage ranges, blocked-modes)
- `backend/tests/test_placeholders.py` — 21 tests for all 5 placeholder types and end-to-end roast filling

### Coverage matrix (post-fix)

`X` = at least one deliverable roast. `—` = blocked by design (personality's `blocked_modes`).

|              | savage_one | sarcastic_friend | toxic_interviewer | startup_investor | professor | gamer |
|--------------|:----------:|:----------------:|:-----------------:|:----------------:|:---------:|:-----:|
| friendly     |     —      |        X         |         —         |         —        |     —     |   —   |
| savage       |     X      |        X         |         X         |         —        |     X     |   X   |
| programmer   |     X      |        X         |         X         |         X        |     X     |   X   |
| student      |     X      |        X         |         —         |         —        |     X     |   —   |
| gamer        |     X      |        X         |         —         |         —        |     —     |   X   |
| corporate    |     X      |        X         |         X         |         X        |     —     |   —   |
| startup      |     X      |        X         |         X         |         X        |     —     |   —   |
| general      |     X      |        X         |         X         |         X        |     X     |   X   |

Every non-blocked cell is now filled. Special templates cover all 6 personalities:
- Openers: 7 (all 6 personalities have ≥1)
- Closers: 6 (all 6 personalities have exactly 1)
- Comebacks: 6 (all 6 personalities have ≥1)
- Callbacks: 3 (savage_one, sarcastic_friend)

### Library stats

- **Roasts:** 183 (unchanged in count; 5 personalities adjusted, 4 personalities added to 4 roasts)
- **Openers:** 7 (was 6)
- **Closers:** 6 (was 3)
- **Comebacks:** 6 (unchanged)
- **Callbacks:** 3 (unchanged)
- **Intents:** 7 (unchanged) with `min_keyword_score` field added
- **Personalities:** 6 (unchanged), `sarcastic_friend.min_damage` lowered 3→1

### API safety contract

Every `/api/session/{sid}/roast` call now runs three guards in order:

1. **Input filter** — `safety.check_input()` scans for self-harm, distress, PII, or minor status. If matched, a safe reply is returned and the session is locked (in the minor case) to `friendly` + `sarcastic_friend`.
2. **Standard roast flow** — intent detect → match → fill → flavor.
3. **Output filter** — `safety.check_output()` + `safety.sanitize_output()` redact any blocked term that slipped through. The `BLOCKED_TERMS` set is empty in this public repo; production deployments extend it internally.

---

## 17. Second Bug Audit (2026-06-02)

After the first round of fixes (174 tests), a second read of the route layer,
models, and matcher surfaced **10 issues** that the test suite would not have
caught on its own. They are all fixed and locked in with regression tests.

### Bugs found & fixed

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 1 | `matcher.apply_personality_flavor` | Called with `None` in `end_session` when no closer exists for the personality → `TypeError: 'NoneType' object is not subscriptable` | Pass `None` through unchanged; caller treats it as "no roast selected" |
| 2 | `routes.py` `/roast` | `MAX_SESSION_MESSAGES=50` defined in config but never enforced → unbounded history growth | Import the cap and return 429 once reached. Safety replies (self-harm) bypass the cap so a user in crisis always gets a safe reply |
| 3 | `models.StartSessionRequest.username` | No length cap. Pydantic default accepts any length | `Field(max_length=64)` + auto-strip + whitespace-only → `None` |
| 4 | `models.RoastRequest.message` | `min_length=1` accepts `"   "` (whitespace) → wastes a recent-roast slot | Custom validator `_no_blank_messages` rejects `str.strip() == ""` |
| 5 | `models.RoastTemplate.weight` | No constraint, despite being used as a probability in matching | `Field(default=1.0, ge=0.0, le=1.0)` |
| 6 | `routes.py` opener / callback / closer | `safety.check_output` only applied to the `/roast` reply text | Output safety is now a defense-in-depth layer on **every** text path that goes to the user (opener, callback, comeback, roast, closer) |
| 7 | `scorer.update_scores` | `is_comeback_failure` parameter was dead code (never read in the body) | Removed from signature; call site updated. `comeback_failures` still flows into `confidence_lost` |
| 8 | `intent.is_comeback` | "HELLO THERE" (all caps, 11 chars, no `!`) was detected as a comeback — noisy false positive | The "all-caps" path now requires `!!` in addition. Phrase and regex signals unchanged |
| 9 | `matcher.select_closer` | Does not filter closers by the personality's `allowed_modes` for the session mode | **Not fixed** — closers are mode-agnostic by design (no `mode` field, work for any personality in any mode). Tracked as a design choice, not a bug |
| 10 | `routes.py` `end_session` | `cl` referenced in `if cl is not None` but only conditionally defined → `NameError` when no closer selected | Initialise `cl: Optional[SpecialTemplate] = None` at the top of the function |

### Bonus fix (found while testing BUG 6)

| Location | Issue | Fix |
|----------|-------|-----|
| `routes.py` `start_session` | `op` was referenced at the bottom (`if op is not None and getattr(op, "reaction", None)...`) but only set in the opener branch. If a callback fired for a returning user, `start_session` crashed with `NameError` | Refactored to a `chosen_special` variable that holds whichever special (callback OR opener) was used. The reaction emoji and output-safety scan both follow the chosen special |

### Defense-in-depth placement

The safety pipeline now runs in this order for every response:

```
input message ──► input safety ─┐
                                ├─► 200 with safe reply OR
                                │     cap check (429, except safety)
                                │     ↓
                                │   match → fill → flavor
                                │     ↓
                                └─► output safety scan + sanitize
```

This way:
- A self-harm or PII message still gets a safe reply **past** the cap.
- A blocked term in any user-facing text (opener, callback, comeback, roast, closer) is redacted before the response leaves the route.
- The library's empty `BLOCKED_TERMS` set keeps the public repo clean; production deployments extend it.

### Test coverage added

- `backend/tests/test_bugfixes.py` — 27 regression tests covering every fix above:
  - `test_apply_personality_flavor_handles_none` / `test_apply_personality_flavor_normal_text`
  - `test_end_session_with_no_closer_does_not_crash` / `test_end_session_does_not_raise_nameerror`
  - `test_session_message_cap_returns_429` / `test_session_cap_bypassed_for_safety_replies`
  - `test_username_too_long_rejected` / `test_username_max_64_accepted` / `test_username_whitespace_treated_as_anonymous` / `test_username_gets_stripped`
  - `test_whitespace_message_rejected` / `test_tab_newline_only_message_rejected` / `test_real_message_with_whitespace_passes`
  - `test_weight_above_one_rejected` / `test_weight_negative_rejected` / `test_weight_zero_accepted` / `test_weight_one_accepted`
  - `test_opener_safety_scan_redacts_blocked_term` / `test_closer_safety_scan_redacts_blocked_term`
  - `test_update_scores_no_longer_takes_failure_flag` / `test_update_scores_basic_call`
  - `test_all_caps_alone_is_not_comeback` / `test_all_caps_with_exclamations_is_comeback` / `test_existing_comeback_signals_still_work` / `test_non_comeback_still_not_comeback`
  - `test_start_session_with_callback_does_not_crash`
  - `test_confidence_lost_caps_at_100`

### Final test status

```
================= 201 passed, 19 skipped in 3.26s ==================
```

- **201 passing** (was 174 — added 27 regression tests)
- **19 skipped** — intentional `blocked_modes` cells in the coverage matrix
- **0 failures**
- All tests run from `pytest backend/tests/` against `python 3.14.4`.

---

**Status:** Layer 1 complete and audit-clean. 229 tests passing. Library at `roast-library/`.
**Owner:** TBD.
**Last updated:** 2026-06-02.

---

## 18. Local Development Runner (2026-06-02)

Spinning up the dev environment used to require two terminals, manual
`.venv\Scripts\activate`, and the right working directory. A single
`run.py` (with cross-platform wrappers) now handles everything.

### One-time setup

| OS | Command |
|----|---------|
| Windows (PowerShell) | `.\setup.ps1` |
| Windows (cmd) | `setup.bat` (uses `run.py` directly) |
| Unix / macOS | `bash setup.sh` |
| Make (any) | `make setup` |

Setup verifies Python 3.10+ and Node 18+, creates `backend/.venv`,
installs `requirements.txt`, and runs `npm install` for the frontend.

### Daily use — one command

| Goal | Command |
|------|---------|
| Run both with HMR (default) | `python run.py` |
| Run both with built frontend | `python run.py --prod` |
| Build, then run with built frontend | `python run.py --build` |
| Backend only (for testing) | `python run.py --backend-only` |
| Frontend only (assumes backend is up) | `python run.py --frontend-only` |
| Custom port | `python run.py --port 9000` |
| No color (CI / piping) | `python run.py --no-color` |
| Windows shortcuts | `run.bat` (cmd) or `.\run.ps1` (PowerShell) |
| Make | `make run` / `make run-prod` / `make run-backend` / `make test` |

`run.py` auto-detects `backend/.venv/Scripts/python.exe` (Windows) or
`backend/.venv/bin/python` (Unix), so the venv does **not** need to be
activated in the calling terminal. Both processes' output is piped to
this terminal with color-coded `[backend]` / `[frontend]` prefixes.
Ctrl+C cleanly tears down both processes (including uvicorn's
multiprocessing reload children on Windows).

### URL output

```
[runner] venv    : E:\projects\degree\AI ROSTER\backend\.venv\Scripts\python.exe
[runner] backend  : ... uvicorn main:app --host 127.0.0.1 --port 8000
[runner] frontend : npm run dev -- -p 3000
[runner] API: http://localhost:8000/api/health
[runner] UI : http://localhost:3000
[runner] press Ctrl+C to stop everything
```

### Files added

- `run.py` — cross-platform launcher (Python stdlib only)
- `run.bat` — cmd shortcut
- `run.ps1` — PowerShell shortcut with `-Prod` / `-Build` / `-BackendOnly` switches
- `setup.ps1` / `setup.sh` — first-time setup
- `Makefile` — `make` shortcuts (cross-platform, where `make` is available)

No new npm or pip dependencies were added.

---

## 19. Layer 1 Loophole Fixes (2026-06-03)

Following a security audit, several production-visible loopholes in Layer 1 were identified and fixed. These fixes are observable at localhost and ready for production deployment.

### 19.1 CORS Configurability
- **Issue**: CORS origins were hardcoded, preventing production lockdown.
- **Fix**: Made `ALLOWED_ORIGINS` configurable via environment variable.
  - Default: `http://localhost:3000` (matches frontend dev server)
  - Production: Set `ALLOWED_ORIGINS` to your actual domain(s)
- **Verification**: 
  ```bash
  # Should be blocked (403)
  curl -H "Origin: http://evil.com" http://localhost:8000/api/health
  
  # Should succeed (200)  
  curl -H "Origin: http://localhost:3000" http://localhost:8000/api/health
  ```

### 19.2 Admin Endpoint Protection
- **Issue**: `/admin/cleanup` endpoint was publicly accessible.
- **Fix**: Added API key authentication via `X-Admin-Key` header.
  - Default key: `dev-secret-change-in-prod` (override via `ADMIN_API_KEY` env var)
  - Returns 403 if missing/invalid
- **Verification**:
  ```bash
  # Should be blocked (403)
  curl http://localhost:8000/admin/cleanup
  
  # Should succeed (200) with correct key
  curl -H "X-Admin-Key: dev-secret-change-in-prod" http://localhost:8000/admin/cleanup
  ```

### 19.3 Rate Limiting
- **Issue**: No rate limiting allowed potential abuse/DoS.
- **Fix**: Added in-memory rate limiter (60 requests/minute per IP by default).
  - Configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` env vars
  - Returns 429 with `Retry-After` header when exceeded
  - Applied to all `/api/` endpoints
- **Verification**:
  ```bash
  # First 60 requests/minute should succeed
  # 61st request should return 429
  for i in {1..65}; do
    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/health
  done | grep -v 200 | head -1
  ```

### 19.4 Safety Blocklist
- **Issue**: `BLOCKED_TERMS` was empty in public repository.
- **Fix**: Added three example blocked terms with clear production guidance.
  - Terms: `badword1`, `badword2`, `badword3` (clearly marked as placeholders)
  - Production must extend with actual blocklist based on safety requirements
  - Terms are redacted with `[redacted]` when detected in output
- **Verification**:
  ```bash
  # Should return roast with badword1 redacted
  curl -X POST http://localhost:8000/api/session/start \
    -H "Content-Type: application/json" \
    -d '{"mode":"savage","personality":"savage_one"}' | jq -r .session_id | \
    read sid && \
  curl -X POST http://localhost:8000/api/session/$sid/roast \
    -H "Content-Type: application/json" \
    -d '{"message":"This contains badword1"}'
  ```

### 19.5 Security Headers
- **Issue**: Missing standard security headers.
- **Fix**: Added middleware to set:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`  
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Server: RoastGPT` (obfuscation)
- **Verification**:
  ```bash
  curl -I http://localhost:8000/api/health
  # Should show the above headers
  ```

### 19.6 Request Size Limit
- **Issue**: No limit on request payload size.
- **Fix**: Set maximum request size to 5MB via FastAPI.
  - Prevents large payload attacks
  - Returns 413 Payload Too Large when exceeded
- **Verification**:
  ```bash
  # Send 6MB payload should return 413
  curl -X POST http://localhost:8000/api/session/start \
    -H "Content-Type: application/json" \
    -d "$(head -c 6000000 /dev/zero | tr '\0' 'a' | jq -R -s -c '{mode:\"savage\",personality:\"savage_one\",message:.}')" \
    -v 2>&1 | grep "< HTTP/"
  ```

### Test Updates
Updated tests in `backend/tests/test_bugfixes.py`:
- `test_cleanup_does_not_remove_live_sessions` - added admin key header
- `test_cleanup_removes_old_ended_sessions` - added admin key header
- All existing tests pass (229 passed, 19 skipped)

### Production Deployment Notes
1. **CORS**: Set `ALLOWED_ORIGINS` to your actual frontend domain(s)
2. **Admin Key**: Change `ADMIN_API_KEY` to a strong secret (use vault/secrets manager)
3. **Rate Limiting**: Tune `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` based on expected traffic
4. **Safety Blocklist**: Extend `BLOCKED_TERMS` in `safety.py` with your actual blocklist
5. **Environment**: All fixes have sensible defaults for development but require configuration for production

---

## 20. User Accounts, Payments, and Personalized Roasts (2026-06-03)

This section documents the production layer added on top of the roast engine: user accounts, JWT auth, Razorpay payments, subscriptions, admin dashboard, chat history persistence, leaderboard, and personalized roasts using the user's name + roaster gender.

### 20.1 Database Layer

ORM: SQLAlchemy 2.0 + `Base.metadata.create_all()` on startup. PostgreSQL in production (auto-fallback to local SQLite for dev when `DATABASE_URL` is unset). Models in `backend/app/db_models.py`:

| Table | Purpose |
|-------|---------|
| `users` | id, email (unique), hashed_password (bcrypt), full_name, gender_preference, is_active, is_verified, is_admin, free_messages_used, created_at |
| `subscription_plans` | id, plan_code, name, price_paise, currency, duration_days, features (JSON) |
| `subscriptions` | id, user_id, plan_id, status, current_period_start/end, cancel_at_period_end, admin_granted, created_at |
| `payments` | id, user_id, razorpay_order_id, razorpay_payment_id, amount, currency, status, description, created_at |
| `chat_history` | id, user_id, session_id, message, is_user, roast_response, score_total, created_at |

### 20.2 Authentication

`backend/app/auth.py` implements:

- **Password hashing**: bcrypt via `passlib` (pinned `bcrypt<4.0.0` for passlib 1.7.4 compatibility).
- **JWT**: `python-jose` with HS256. Two token types: `access` (30 min) and `refresh` (7 days). Secret in `JWT_SECRET_KEY` (≥32 bytes).
- **FastAPI dependencies**: `get_current_user` (401 on missing/invalid), `get_optional_user` (returns None for anonymous), `require_admin` (403 on non-admin).

Routes (`backend/app/auth_routes.py`):

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/auth/register` | none | Create user, return access + refresh tokens |
| `POST /api/auth/login` | none | Verify password, return tokens |
| `POST /api/auth/refresh` | none | Exchange refresh token for new access token |
| `GET  /api/auth/me` | bearer | Current user profile |
| `PATCH /api/auth/me` | bearer | Update name / gender_preference |
| `POST /api/auth/change-password` | bearer | Change password (requires current) |

### 20.3 Payments (Razorpay)

`backend/app/payment_routes.py`:

- `GET  /api/payments/plans` — public; returns 3 default plans seeded on startup:
  - `starter`: ₹299 / 10 days, male + female roaster
  - `pro`:    ₹799 / 30 days, all 3 roasters, priority support
  - `legend`: ₹1999 / 90 days, custom personality
- `POST /api/payments/create-order` — bearer; creates a Razorpay order and returns `order_id`, `amount`, `currency`, `key_id`.
- `POST /api/payments/verify` — bearer; verifies the HMAC-SHA256 signature, marks the payment `captured`, creates an active `Subscription` for the user.
- `POST /api/payments/webhook` — public; signature-verified; handles `payment.captured`, `payment.failed`, `subscription.cancelled`.
- `GET  /api/payments/history` — bearer; user's past payments.

Subscription routes (`backend/app/subscription_routes.py`):

- `GET  /api/subscriptions/me` — user's current + past subscriptions.
- `POST /api/subscriptions/cancel` — sets `cancel_at_period_end=True`; user keeps access until `current_period_end`.

### 20.4 Admin Dashboard

`backend/app/admin_routes.py` (all require `is_admin=True`):

| Endpoint | Purpose |
|----------|---------|
| `GET  /api/admin/stats` | Total / active users, active subs, total payments, total revenue |
| `GET  /api/admin/users` | Paginated user list with optional search by email/name |
| `GET  /api/admin/users/{id}` | Single user details |
| `PATCH /api/admin/users/{id}` | Toggle `is_active` / `is_verified` / `is_admin` (refuses self-demotion) |
| `POST /api/admin/grant-subscription` | Create an active subscription for a user (no payment) — support / promos / leaderboard rewards |
| `GET  /api/admin/leaderboard` | Top N users by total damage for current week / month |

### 20.5 Chat History

`backend/app/history_routes.py`:

- `GET  /api/history` — bearer; paginated chat history (newest first).
- `DELETE /api/history` — bearer; clear all of the user's history.

History is also persisted automatically on `/api/session/{id}/roast`, `/api/session/start` (opener), and `/api/session/{id}/end` (closer) when the request carries a valid JWT. Writes are best-effort: a DB error never breaks the roast response.

### 20.6 Public Leaderboard

`backend/app/leaderboard_routes.py` exposes `/api/leaderboard` (no auth). It returns `display_name` (full_name or email prefix) and `masked_email` (e.g. `le***@example.com`) so PII is never leaked. Periods: `week`, `month`, `all`. The frontend `/leaderboard` page consumes this directly.

### 20.7 Personalized Roasts

A new `roaster` placeholder type joins the existing five (`enum`, `context`, `intent`, `history`, `username`).

**Schema change** (`roast-library/schema.json`): the `type` enum now includes `"roaster"`.

**Engine change** (`backend/app/filler.py`): `_roaster_value` resolves a placeholder like `{roaster_pronoun}` to a gender-aware value. The session model carries `roaster_gender: "male" | "female" | "neutral"`, populated by `/api/session/start` from the new optional `roaster_gender` field on the request body. The frontend reads the user's saved preference from `/api/auth/me` and passes it.

**Library change** (`roast-library/roasts/savage.json`): 4 new roasts (sav_025 to sav_028) and 2 new openers (opn_008, opn_009) and 1 new closer (cls_006) use the new placeholders. The total roast-library is now 187 roasts.

**Built-in defaults** for the standard roaster placeholders:

| Placeholder | male | female | neutral |
|-------------|------|--------|---------|
| `roaster_pronoun`     | he   | she    | they  |
| `roaster_pronoun_obj` | him  | her    | them  |
| `roaster_pronoun_poss`| his  | her    | their |
| `roaster_title`       | sir  | ma'am  | friend|
| `roaster_self`        | man  | lady   | friend|

Templates can override these by passing `values: ["male:he", "female:she", "neutral:they"]` to the placeholder spec.

### 20.8 Free-Tier Gate

Anonymous users (no JWT) and free users (no active subscription) get 5 messages per session. The 6th message returns `402 Payment Required` with `detail: "Free tier limit reached (5 messages). Subscribe to keep roasting."`. The frontend maps this to a friendly error + "See plans →" button pointing at `/pricing`. `free_messages_used` is incremented for free authenticated users (best-effort).

### 20.9 Frontend Pages

| Route | Purpose |
|-------|---------|
| `/login`         | Email + password sign-in |
| `/register`      | Sign-up with gender preference picker |
| `/pricing`       | 3 plans + Razorpay checkout widget |
| `/account`       | Profile, subscription, payment history, cancel |
| `/history`       | Paginated, day-grouped chat history with "Clear all" |
| `/admin`         | 4-tab dashboard: stats / users / grant / leaderboard |
| `/leaderboard`   | Public board, week/month/all tabs (replaced mock) |

The `lib/auth-api.ts` client auto-injects `Authorization: Bearer <token>` from localStorage; `lib/api.ts` (the chat client) does the same so the same fetch wrapper serves the whole app.

### 20.10 Deployment (no Docker)

`render.yaml` declares the FastAPI service + Postgres database. `vercel.json` configures the Next.js deploy. `DEPLOY.md` walks through both with screenshots-free, copy-paste steps. The `scripts/bootstrap_admin.py` one-shot creates the first admin user.

### 20.11 Test Coverage

256 tests pass, 19 skipped, 1 warning, ~13 s.

- `test_auth.py`: 22 tests — register/login/refresh/me, change-password, plans, admin guards, history auth, public leaderboard (no auth, period validation, email masking).
- `test_placeholders.py`: 27 tests (5 new for the `roaster` type) — explicit values, neutral fallback, built-in defaults, unknown-gender coercion, end-to-end fill with `{username}` + `{roaster_pronoun}` together.

### 20.12 Critical Environment Variables

```
DATABASE_URL=postgresql://user:pass@host:5432/dbname   # production
JWT_SECRET_KEY=<32+ byte random string>
ADMIN_API_KEY=<random string>
RAZORPAY_KEY_ID=rzp_live_xxx                           # rzp_test_xxx for staging
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx
ALLOWED_ORIGINS=https://your-frontend.example.com
FRONTEND_URL=https://your-frontend.example.com
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW=60
```

See `.env.example` for the full list with documentation.

