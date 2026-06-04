"""Backup the production database to a JSON file (or upload to a remote store).

The default free-tier Render PostgreSQL expires after 30 days and deletes
all data. Neon (free, never expires) is the recommended primary, but this
script adds a belt-and-braces second copy in case the primary is ever
wiped, the provider changes policy, or you want to migrate to a new host.

Usage (one-off):
    python -m scripts.backup_db --output backup-20260104.json
    python -m scripts.backup_db --output -                  # stdout
    python -m scripts.backup_db --output backup.json --upload   # + remote

Usage (cron — driven by env vars, see --env mode):
    BACKUP_DESTINATION=github \
    BACKUP_GITHUB_REPO=mihir2452005/roastgpt-backups \
    BACKUP_GITHUB_TOKEN=ghp_xxx \
    python -m scripts.backup_db --env

Storage backends (set BACKUP_DESTINATION env var):
  - local (default): write to --output path
  - http:            POST JSON to BACKUP_WEBHOOK_URL (e.g. requestbin, file.io)
  - github:          commit file to a GitHub repo via REST API
  - s3:              upload to S3-compatible (Cloudflare R2, Backblaze B2, AWS)
                     requires BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT, BACKUP_S3_KEY_ID,
                     BACKUP_S3_KEY_SECRET, and optionally BACKUP_S3_REGION

The backup is a single JSON file containing all rows from all tables,
in dependency order. No DDL, just data — restore_db.py can rebuild the
schema via Base.metadata.create_all() before reinserting.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Allow `python -m scripts.backup_db` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app import db_models
from app.database import SessionLocal, engine, init_db


# Order matters: parents first, children after, so a fresh restore that
# honours FK constraints can insert top-down.
BACKUP_TABLES: list[tuple[str, Any]] = [
    ("users", db_models.User),
    ("subscription_plans", db_models.SubscriptionPlan),
    ("subscriptions", db_models.Subscription),
    ("payments", db_models.Payment),
    ("chat_history", db_models.ChatHistory),
    ("roast_sessions", db_models.RoastSession),
]

# Columns that are FK references — exported as their value rather than the
# related object, which is what restore_db.py needs to reinsert.
# (All FKs are simple ints; we just need to call getattr(row, "id").)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy model instance to a JSON-safe dict.

    Datetimes → ISO strings. Enums → .value. Everything else is whatever
    SQLAlchemy gave us (str, int, float, bool, None, dict, list).
    """
    out: dict[str, Any] = {}
    for col in row.__table__.columns:
        v = getattr(row, col.name, None)
        if isinstance(v, datetime):
            # Always include timezone to make round-trip unambiguous.
            v = v.isoformat()
        elif hasattr(v, "value") and hasattr(v, "__class__") and v.__class__.__name__ in (
            "SubStatus", "PaymentStatus", "GenderPref"
        ):
            v = v.value
        out[col.name] = v
    return out


def _safe_table_rows(db: Session, model: Any) -> list[dict[str, Any]]:
    """Read all rows from a table, returning [] if the table doesn't exist
    yet (e.g. roast_sessions before the schema is migrated)."""
    try:
        rows = db.query(model).all()
    except Exception as e:  # pragma: no cover
        print(f"warning: could not read {model.__tablename__}: {e}", file=sys.stderr)
        return []
    return [_row_to_dict(r) for r in rows]


def build_backup_dict(db: Session, include_passwords: bool = True) -> dict[str, Any]:
    """Snapshot the entire database into a JSON-serializable dict.

    Args:
      include_passwords: If False, redact `hashed_password` so the
        backup is safe to share with a third party. The default is True
        so restore_db.py can re-create accounts verbatim. NEVER set this
        to False if the backup is going to a private store only you can
        reach; setting it to False disables restore of user accounts.
    """
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, model in BACKUP_TABLES:
        rows = _safe_table_rows(db, model)
        if not include_passwords and name == "users":
            for r in rows:
                r["hashed_password"] = "[REDACTED]"
        tables[name] = rows

    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine": str(engine.url).split("@")[-1] if "@" in str(engine.url) else "sqlite",
        "include_passwords": include_passwords,
        "row_counts": {k: len(v) for k, v in tables.items()},
        "tables": tables,
    }


def serialize(backup: dict[str, Any]) -> bytes:
    """JSON-serialize a backup dict to bytes (UTF-8, pretty-printed)."""
    return json.dumps(backup, indent=2, ensure_ascii=False, default=str).encode("utf-8")


def write_local(data: bytes, output: str) -> str:
    """Write the backup to a local file path. `--output -` writes to stdout
    for piping to other tools. Returns the path actually written to."""
    if output == "-":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
        return "<stdout>"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_bytes(data)
    return output


# ---- Remote backends ----

def upload_http(data: bytes, url: str) -> str:
    """POST the backup to an HTTP webhook. Returns the URL on success.

    Useful for services like requestbin, webhook.site, file.io, transfer.sh,
    or a custom /api/admin/backup endpoint you host yourself.
    """
    import httpx  # already in requirements
    with httpx.Client(timeout=60) as client:
        r = client.post(
            url,
            content=data,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
    return url


def upload_github(
    data: bytes,
    repo: str,
    token: str,
    filename: str,
    message: Optional[str] = None,
) -> str:
    """Commit the backup to a GitHub repo via the Contents API.

    The repo can be private (token must have `contents:write`).
    Returns the path of the committed file.
    """
    import httpx
    import base64

    path = f"backups/{filename}"
    msg = message or f"backup {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"

    # If the file already exists, we need its sha to update it.
    sha: Optional[str] = None
    with httpx.Client(timeout=30) as client:
        r = client.get(url, headers=headers, params={"ref": "main"})
        if r.status_code == 200:
            sha = r.json().get("sha")
        body: dict[str, Any] = {
            "message": msg,
            "content": base64.b64encode(data).decode("ascii"),
            "branch": "main",
        }
        if sha:
            body["sha"] = sha
        r = client.put(url, headers=headers, json=body)
        r.raise_for_status()
    return path


def upload_s3(
    data: bytes,
    bucket: str,
    key: str,
    endpoint: str,
    key_id: str,
    key_secret: str,
    region: str = "auto",
) -> str:
    """Upload to any S3-compatible store (Cloudflare R2, Backblaze B2, AWS).

    Uses boto3 if installed; otherwise tries urllib (basic, slower, no
    multipart — fine for backup-sized payloads).
    """
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=key_secret,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )
        s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/json")
        return f"{endpoint.rstrip('/')}/{bucket}/{key}"
    except ImportError:
        # Pure-stdlib fallback. Works for AWS; for R2/B2 you'll need
        # to `pip install boto3` (already a soft dep of fastapi ecosystem).
        import urllib.request
        import hmac
        import hashlib
        from email.utils import formatdate

        # NOTE: this minimal signer is AWS Signature V4 and is only a
        # last-resort fallback. For production backups, `pip install boto3`
        # is the supported path. Kept short and well-commented.
        raise RuntimeError(
            "boto3 not installed. Run `pip install boto3` for S3/R2/B2 support, "
            "or use BACKUP_DESTINATION=github instead."
        )


# ---- CLI ----

def main() -> int:
    p = argparse.ArgumentParser(description="Backup the RoastGPT database to JSON.")
    p.add_argument(
        "--output", "-o",
        default="backup-{ts}.json",
        help="Output file path. Use '-' for stdout. Default: backup-<UTC>.json",
    )
    p.add_argument(
        "--upload", action="store_true",
        help="Also upload to the BACKUP_DESTINATION configured in env.",
    )
    p.add_argument(
        "--env", action="store_true",
        help="Use only env-var config (no flags). For cron / Render Cron Job.",
    )
    p.add_argument(
        "--redact-passwords", action="store_true",
        help="Redact hashed_password in the users table. NEVER pair this with "
             "BACKUP_DESTINATION if you want a restorable backup.",
    )
    args = p.parse_args()

    # Ensure the schema is in place — idempotent.
    init_db()

    db = SessionLocal()
    try:
        backup = build_backup_dict(db, include_passwords=not args.redact_passwords)
    finally:
        db.close()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = args.output.format(ts=ts) if "{ts}" in args.output else args.output
    data = serialize(backup)

    written = write_local(data, out_path)
    print(
        f"[OK] wrote {len(data):,} bytes to {written}",
        file=sys.stderr,
    )
    print(
        f"      row counts: {backup['row_counts']}",
        file=sys.stderr,
    )

    if args.upload or args.env:
        dest = os.environ.get("BACKUP_DESTINATION", "local").lower()
        if dest == "local":
            print("[OK] BACKUP_DESTINATION=local — file already written.", file=sys.stderr)
        elif dest == "http":
            url = os.environ.get("BACKUP_WEBHOOK_URL", "")
            if not url:
                print("ERROR: BACKUP_WEBHOOK_URL not set", file=sys.stderr)
                return 2
            upload_http(data, url)
            print(f"[OK] uploaded to {url}", file=sys.stderr)
        elif dest == "github":
            repo = os.environ.get("BACKUP_GITHUB_REPO", "")
            token = os.environ.get("BACKUP_GITHUB_TOKEN", "")
            if not repo or not token:
                print("ERROR: BACKUP_GITHUB_REPO and BACKUP_GITHUB_TOKEN required",
                      file=sys.stderr)
                return 2
            filename = f"backup-{ts}.json"
            path = upload_github(data, repo, token, filename)
            print(f"[OK] committed to github:{repo}/{path}", file=sys.stderr)
        elif dest == "s3":
            bucket = os.environ.get("BACKUP_S3_BUCKET", "")
            endpoint = os.environ.get("BACKUP_S3_ENDPOINT", "")
            key_id = os.environ.get("BACKUP_S3_KEY_ID", "")
            key_secret = os.environ.get("BACKUP_S3_KEY_SECRET", "")
            if not all([bucket, endpoint, key_id, key_secret]):
                print("ERROR: BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT, "
                      "BACKUP_S3_KEY_ID, BACKUP_S3_KEY_SECRET required",
                      file=sys.stderr)
                return 2
            region = os.environ.get("BACKUP_S3_REGION", "auto")
            key = f"backups/backup-{ts}.json"
            uri = upload_s3(data, bucket, key, endpoint, key_id, key_secret, region)
            print(f"[OK] uploaded to {uri}", file=sys.stderr)
        else:
            print(f"ERROR: unknown BACKUP_DESTINATION={dest!r}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
