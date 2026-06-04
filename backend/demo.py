"""Quick end-to-end demo of the roast engine."""
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from main import app
from fastapi.testclient import TestClient


def main():
    with TestClient(app) as c:
        # Health
        h = c.get("/api/health").json()
        print(f"HEALTH: {h['roasts']} roasts, {h['personalities']} personalities, {h['intents']} intents")
        print()

        # Start a session
        r = c.post("/api/session/start", json={
            "mode": "savage",
            "personality": "savage_one",
            "username": "Alice",
        })
        d = r.json()
        sid = d["session_id"]
        print(f"OPENER: {d['opener']}")
        print()

        # Send various messages
        for msg in [
            "My code has 47 bugs in production and I pushed to main on Friday",
            "I have an exam tomorrow and I have not studied at all",
            "My startup is a Notion doc and a Squarespace domain with 0 customers",
            "no u",
        ]:
            r = c.post(f"/api/session/{sid}/roast", json={"message": msg})
            d = r.json()
            print(f"USER: {msg}")
            print(f"ROAST: {d['roast']}")
            print(f"INTENTS: {d['intents_detected']}")
            print(f"SCORES: damage={d['scores']['emotional_damage']} | confidence_lost={d['scores']['confidence_lost']} | reality_checks={d['scores']['reality_checks']} | comeback={d['is_comeback']}")
            print()

        # End
        r = c.post(f"/api/session/{sid}/end")
        d = r.json()
        print(f"CLOSER: {d['closer']}")
        print(f"FINAL: {json.dumps(d['final_scores'], indent=2)}")
        print(f"SHARE: {d['share_url']}")


if __name__ == "__main__":
    main()
