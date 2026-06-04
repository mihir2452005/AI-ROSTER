"""Diagnostic: list the contents of the current database.

Useful for verifying that a backup covered everything, debugging free-tier
issues, or sanity-checking a fresh deployment. Prints to stdout in a
human-friendly format, or to JSON with --json.

Usage:
    python -m scripts.list_db
    python -m scripts.list_db --json
    python -m scripts.list_db --table users
    python -m scripts.list_db --user-email someone@example.com
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Allow `python -m scripts.list_db` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import db_models
from app.database import SessionLocal


# Tables we know about. Display order matches RESTORE_TABLES.
ALL_TABLES: list[tuple[str, Any]] = [
    ("users", db_models.User),
    ("subscription_plans", db_models.SubscriptionPlan),
    ("subscriptions", db_models.Subscription),
    ("payments", db_models.Payment),
    ("chat_history", db_models.ChatHistory),
    ("roast_sessions", db_models.RoastSession),
]


def _row_to_jsonable(row: Any) -> dict[str, Any]:
    """Strip a row to a JSON-safe dict. Datetimes → ISO strings."""
    out: dict[str, Any] = {}
    for col in row.__table__.columns:
        v = getattr(row, col.name, None)
        if isinstance(v, datetime):
            v = v.isoformat()
        elif v is not None and hasattr(v, "value") and v.__class__.__name__ in (
            "SubStatus", "PaymentStatus", "GenderPref"
        ):
            v = v.value
        out[col.name] = v
    return out


def _print_table(db: Session, model: Any) -> int:
    """Print a single table's contents. Returns row count."""
    rows = db.query(model).all()
    if not rows:
        print(f"  (empty)")
        return 0
    cols = [c.name for c in model.__table__.columns]
    # Width per column: header vs longest cell.
    widths = {c: max(len(c), 12) for c in cols}
    str_rows: list[list[str]] = []
    for r in rows:
        d = _row_to_jsonable(r)
        sr = []
        for c in cols:
            v = d.get(c)
            sv = "" if v is None else str(v)
            sv = sv[:80]  # cap for readability
            widths[c] = min(40, max(widths[c], len(sv)))
            sr.append(sv)
        str_rows.append(sr)
    # Print.
    def fmt(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[c]) for c, c_val in zip(cols, cells))
    print(f"  {fmt(cols)}")
    print(f"  {fmt(['-' * widths[c] for c in cols])}")
    for sr in str_rows:
        print(f"  {fmt(sr)}")
    return len(rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect the RoastGPT database.")
    p.add_argument("--json", action="store_true", help="Output as JSON.")
    p.add_argument("--table", default=None, help="Show contents of a single table.")
    p.add_argument("--user-email", default=None, help="Show one user's full record.")
    p.add_argument("--user-id", type=int, default=None, help="Show one user's full record.")
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.json:
            out: dict[str, Any] = {"tables": {}}
            for name, model in ALL_TABLES:
                rows = db.query(model).all()
                out["tables"][name] = {
                    "count": len(rows),
                    "rows": [_row_to_jsonable(r) for r in rows],
                }
            if args.user_email or args.user_id:
                q = db.query(db_models.User)
                if args.user_email:
                    q = q.filter(db_models.User.email == args.user_email)
                if args.user_id:
                    q = q.filter(db_models.User.id == args.user_id)
                user = q.first()
                out["user"] = _row_to_jsonable(user) if user else None
            print(json.dumps(out, indent=2, default=str))
            return 0

        # Human mode.
        print("=" * 60)
        print("RoastGPT database contents")
        print("=" * 60)

        # Single-table short-circuit.
        if args.table:
            model = next((m for n, m in ALL_TABLES if n == args.table), None)
            if model is None:
                print(f"ERROR: unknown table {args.table!r}", file=sys.stderr)
                return 2
            print(f"\n[{args.table}]")
            n = _print_table(db, model)
            print(f"\n{args.table}: {n} row(s)")
            return 0

        # User short-circuit.
        if args.user_email or args.user_id:
            q = db.query(db_models.User)
            if args.user_email:
                q = q.filter(db_models.User.email == args.user_email)
            if args.user_id:
                q = q.filter(db_models.User.id == args.user_id)
            user = q.first()
            if user is None:
                print("user not found")
                return 0
            print(f"\n[user] {user.email} (id={user.id})")
            print(f"  full_name:     {user.full_name}")
            print(f"  is_admin:      {user.is_admin}")
            print(f"  is_active:     {user.is_active}")
            print(f"  free_used:     {user.free_messages_used}/5")
            print(f"  token_version: {user.token_version}")
            print(f"  created_at:    {user.created_at}")

            subs = db.query(db_models.Subscription).filter(
                db_models.Subscription.user_id == user.id
            ).all()
            print(f"\n  subscriptions ({len(subs)}):")
            for s in subs:
                print(f"    id={s.id} status={s.status.value} "
                      f"period_end={s.current_period_end} "
                      f"admin_granted={s.admin_granted}")

            history = db.query(db_models.ChatHistory).filter(
                db_models.ChatHistory.user_id == user.id
            ).order_by(db_models.ChatHistory.created_at.desc()).limit(5).all()
            print(f"\n  last 5 history rows:")
            for h in history:
                print(f"    {h.created_at} is_user={h.is_user} "
                      f"session={h.session_id or '-'} "
                      f"msg={h.message[:60]!r}")
            return 0

        # Default: counts per table.
        for name, model in ALL_TABLES:
            count = db.query(func.count()).select_from(model).scalar() or 0
            print(f"  {name:<24} {count:>6} row(s)")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
