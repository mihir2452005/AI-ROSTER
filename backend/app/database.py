"""Database connection and session management."""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session


DATABASE_URL = os.environ.get("DATABASE_URL", "")

# If no DATABASE_URL is set, we fall back to a SQLite local file for dev/testing
# In production on Render/Vercel, this MUST be set to a PostgreSQL URL
if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
elif DATABASE_URL:
    # Assume it's a SQLAlchemy-compatible URL (e.g. sqlite:///./test.db)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    # Dev fallback: SQLite
    DB_FILE = os.environ.get("SQLITE_FILE", "roastgpt_dev.db")
    engine = create_engine(
        f"sqlite:///{DB_FILE}",
        connect_args={"check_same_thread": False},
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Call this on startup."""
    from . import db_models  # noqa: F401 - Import models so SQLAlchemy sees them
    Base.metadata.create_all(bind=engine)
