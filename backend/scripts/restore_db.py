"""Restore a database from a JSON backup produced by backup_db.py.

Usage:
    python -m scripts.restore_db --input backup-20260104.json
    python -m scripts.restore_db --input backup.json --dry-run
    python -m scripts.restore_db --input backup.json --only users,chat_history
    python -m scripts.restore_db --input backup.json --truncate   # wipe first

The restore works in two modes:
  * Append (default): adds rows alongside whatever is currently in the
    target database. For tables with a serial primary key this can
    collide on `id`; use --truncate first if you want a clean import.
  * Truncate-then-insert (--truncate): deletes every row from each
    target table first, then re-inserts from the backup. This is the
    right mode for a migration from one provider to another.

The script is idempotent in --truncate mode. Run it twice with the same
backup and the second run is a no-op.

The schema is created with Base.metadata.create_all() before any
import, so this script can be used against a brand-new database
(including a fresh Neon project) with no other setup.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Allow `python -m scripts.restore_db` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app import db_models
from app.database import Base, SessionLocal, engine, init_db


# Keep these in sync with backup_db.py.
RESTORE_TABLES: list[tuple[str, Any]] = [
    ("users", db_models.User),
    ("subscription_plans", db_models.SubscriptionPlan),
    ("subscriptions", db_models.Subscription),
    ("payments", db_models.Payment),
    ("chat_history", db_models.ChatHistory),
    ("roast_sessions", db_models.RoastSession),
]


def _coerce_datetime(value: Any) -> Any:
    """Convert an ISO string back into a datetime, pass through None, and
    leave other types alone. Defensive against a backup that stored
    timezone-naive datetimes (older versions of backup_db.py)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # `fromisoformat` accepts the "...+00:00" form we write.
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        if dt.tzinfo is None:
            # Treat naive datetimes as UTC. This is the safest guess
            # because backup_db.py only writes tz-aware values; naive
            # data means someone hand-edited the backup.
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return value


def _coerce_enum(value: Any, enum_cls: Any) -> Any:
    """If the column is a SQLAlchemy Enum, convert string values to the
    enum member. Pass through None."""
    if value is None:
        return None
    if hasattr(enum_cls, "__members__") and isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            return value
    return value


def _row_kwargs(model: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Translate a JSON dict into kwargs for a SQLAlchemy model.

    * Strips unknown keys (forward-compat with new columns).
    * Converts ISO strings to datetimes (always, for every column).
    * Converts string enum values to enum members.
    """
    out: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.name not in data:
            continue
        v = data[col.name]
        # Datetime columns: always coerce. SQLite raises TypeError on
        # string input ("SQLite DateTime type only accepts Python
        # datetime and date objects as input"), and PostgreSQL is
        # stricter about tz-aware inputs. Our _coerce_datetime handles
        # both datetime instances (passthrough) and ISO strings.
        col_type = col.type
        is_datetime = (
            "DATETIME" in str(type(col_type).__name__).upper()
            or "DATETIME" in str(col_type).upper()
        )
        if is_datetime:
            v = _coerce_datetime(v)
        # SQLAlchemy stores enums as Python enums on the model attribute.
        if hasattr(col_type, "enum_class") and col_type.enum_class is not None:
            v = _coerce_enum(v, col_type.enum_class)
        out[col.name] = v
    return out


def restore_table(
    db: Session,
    model: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Insert rows into a table. Returns (inserted, skipped) counts.

    Skipped = rows that were filtered because they referenced a missing
    parent row (FK violation). The backup is exported in parent-first
    order so this should be 0 in normal use.
    """
    if not rows:
        return 0, 0
    if dry_run:
        return len(rows), 0
    inserted = 0
    skipped = 0
    for data in rows:
        kwargs = _row_kwargs(model, data)
        if not kwargs:
            skipped += 1
            continue
        try:
            db.add(model(**kwargs))
            db.flush()  # surface FK errors here, not at commit time
            inserted += 1
        except Exception as e:  # pragma: no cover - depends on data
            db.rollback()
            skipped += 1
            print(
                f"warning: skipped row in {model.__tablename__}: {e}",
                file=sys.stderr,
            )
    return inserted, skipped


def truncate_table(db: Session, model: Any) -> int:
    """Delete every row from a table. Returns the number of rows removed."""
    n = db.query(model).delete()
    db.commit()
    return n


def load_backup(path: str) -> dict[str, Any]:
    """Read and validate a backup JSON file. Raises ValueError on error."""
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"backup file is not valid JSON: {e}") from e
    if not isinstance(data, dict) or "tables" not in data:
        raise ValueError(
            "backup file is missing the top-level 'tables' object. "
            "Was this produced by scripts.backup_db?"
        )
    return data


def main() -> int:
    p = argparse.ArgumentParser(
        description="Restore the RoastGPT database from a JSON backup."
    )
    p.add_argument(
        "--input", "-i", required=True,
        help="Path to the backup JSON file (output of backup_db.py).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be restored without touching the database.",
    )
    p.add_argument(
        "--truncate", action="store_true",
        help="DELETE every row from the target tables before restoring. "
             "Required for a clean import from another provider.",
    )
    p.add_argument(
        "--only", default=None,
        help="Comma-separated list of table names to restore (e.g. users,chat_history). "
             "Default: all tables in dependency order.",
    )
    args = p.parse_args()

    backup = load_backup(args.input)
    tables_data: dict[str, list[dict[str, Any]]] = backup.get("tables", {})

    only: Optional[set[str]] = None
    if args.only:
        only = {t.strip() for t in args.only.split(",") if t.strip()}

    # Filter tables to those requested.
    plan = [(n, m) for n, m in RESTORE_TABLES if n in tables_data and (not only or n in only)]
    if only:
        # Surface unknown names early so a typo doesn't silently no-op.
        unknown = only - {n for n, _ in RESTORE_TABLES}
        if unknown:
            print(f"ERROR: unknown table name(s) in --only: {sorted(unknown)}", file=sys.stderr)
            print(f"       valid: {[n for n, _ in RESTORE_TABLES]}", file=sys.stderr)
            return 2

    # If a parent table is excluded, the child tables can't be restored
    # cleanly. Bail out rather than producing a half-restored database.
    if only:
        table_names = {n for n, _ in plan}
        # FK parents: users -> subscriptions/payments/chat_history/roast_sessions
        #             subscription_plans -> subscriptions
        #             subscriptions -> payments
        needs_users = {"subscriptions", "payments", "chat_history", "roast_sessions"}
        needs_plans = {"subscriptions"}
        needs_subscriptions = {"payments"}
        for needed, table in (
            (needs_users, "users"),
            (needs_plans, "subscription_plans"),
            (needs_subscriptions, "subscriptions"),
        ):
            if any(t in table_names for t in needed) and table not in table_names:
                print(
                    f"ERROR: --only includes tables that depend on {table!r}; "
                    f"either include {table!r} or remove the dependent tables.",
                    file=sys.stderr,
                )
                return 2

    print(f"backup: {args.input}", file=sys.stderr)
    print(f"  created_at: {backup.get('created_at', '?')}", file=sys.stderr)
    print(f"  row counts: { {k: len(v) for k, v in tables_data.items()} }", file=sys.stderr)
    if not args.dry_run:
        print(f"  mode: {'truncate + insert' if args.truncate else 'append'}", file=sys.stderr)
    else:
        print(f"  mode: dry-run (no DB writes)", file=sys.stderr)
    print(f"  restoring: {[n for n, _ in plan]}", file=sys.stderr)

    if args.dry_run:
        # Just print, no schema creation, no DB connect.
        return 0

    # Ensure schema exists.
    init_db()

    db = SessionLocal()
    try:
        totals: dict[str, tuple[int, int]] = {}
        for name, model in plan:
            if args.truncate:
                removed = truncate_table(db, model)
                print(f"[truncate] {name}: {removed} row(s) removed", file=sys.stderr)
            inserted, skipped = restore_table(
                db, model, tables_data.get(name, []), dry_run=False
            )
            totals[name] = (inserted, skipped)
            print(
                f"[restore]  {name}: {inserted} inserted, {skipped} skipped",
                file=sys.stderr,
            )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"ERROR: restore failed: {e}", file=sys.stderr)
        return 3
    finally:
        db.close()

    total_in = sum(i for i, _ in totals.values())
    total_skip = sum(s for _, s in totals.values())
    print(
        f"[OK] restored {total_in} rows, skipped {total_skip}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
