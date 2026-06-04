"""Bootstrap the first admin user.

Run this once after deploying to give yourself admin access. It registers
the user (or upgrades an existing one to admin). Use a strong password.

Usage (on the deployed service, e.g. via Render Shell):
    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=YourStrongPass123 \\
        python -m scripts.bootstrap_admin

Or locally (after pointing DATABASE_URL at production):
    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=YourStrongPass123 \\
        python -m scripts.bootstrap_admin
"""
from __future__ import annotations

import os
import sys
from getpass import getpass

# Allow running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    full_name = os.environ.get("ADMIN_NAME", "Admin").strip()

    if not email:
        email = input("Admin email: ").strip().lower()
    if not password:
        password = getpass("Admin password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1
    if "@" not in email or "." not in email.split("@")[-1]:
        print("Email looks invalid.", file=sys.stderr)
        return 1

    from app import auth, db_models
    from app.database import SessionLocal, init_db
    from sqlalchemy import select

    # Ensure tables exist (idempotent).
    init_db()

    db = SessionLocal()
    try:
        user = db.execute(
            select(db_models.User).where(db_models.User.email == email)
        ).scalar_one_or_none()

        if user is None:
            user = db_models.User(
                email=email,
                full_name=full_name,
                hashed_password=auth.hash_password(password),
                gender_preference=db_models.GenderPref.neutral,
                is_verified=True,
                is_admin=True,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[OK] Created admin user: {user.email} (id={user.id})")
        else:
            user.is_admin = True
            user.is_active = True
            user.is_verified = True
            # Reset password so the bootstrap can also recover a locked-out admin
            user.hashed_password = auth.hash_password(password)
            db.commit()
            print(f"[OK] Upgraded existing user to admin: {user.email} (id={user.id})")

        print("You can now sign in at /login with the credentials above.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
