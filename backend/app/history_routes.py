"""Chat history routes - users can view, search, and delete their
past conversations. Chat history is persisted when a user is
authenticated. Anonymous sessions continue to work but their history
is not persisted across server restarts.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from . import auth, auth_schemas, db_models
from .database import get_db

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=auth_schemas.ChatHistoryResponse)
def my_history(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    q: Optional[str] = Query(None, max_length=200,
                             description="Case-insensitive substring search over message + roast_response"),
) -> auth_schemas.ChatHistoryResponse:
    """Return the authenticated user's chat history, newest first.

    `q` enables a server-side substring search — it scans the
    user's own rows only (the `WHERE user_id = ?` filter is
    non-negotiable). Use the `?q=` param for full-text-ish search
    on a personal history; this isn't a global search index.
    """
    base = db.query(db_models.ChatHistory).filter(
        db_models.ChatHistory.user_id == user.id
    )
    if q:
        like = f"%{q.lower()}%"
        base = base.filter(
            or_(
                func.lower(db_models.ChatHistory.message).like(like),
                func.lower(func.coalesce(db_models.ChatHistory.roast_response, "")).like(like),
            )
        )
    total = base.count()
    items = (
        base.order_by(db_models.ChatHistory.created_at.desc())
        .offset(skip).limit(limit).all()
    )

    return auth_schemas.ChatHistoryResponse(
        items=[
            auth_schemas.ChatHistoryItem(
                id=item.id,
                message=item.message,
                is_user=item.is_user,
                roast_response=item.roast_response,
                score_total=item.score_total,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
    )


@router.delete("")
def clear_history(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Delete the authenticated user's chat history. Cannot be undone."""
    deleted = db.query(db_models.ChatHistory).filter(
        db_models.ChatHistory.user_id == user.id
    ).delete()
    db.commit()
    return {"message": "History cleared", "deleted": deleted}


# ----- Export -----


@router.get("/export")
def export_history(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    format: str = Query("txt", pattern="^(txt|md|json)$"),
) -> Response:
    """Export the user's full chat history as a downloadable file.

    Formats:
      - txt:  plain-text transcript, one message per paragraph
      - md:   Markdown with headers per day
      - json: structured JSON
    """
    items = (
        db.query(db_models.ChatHistory)
        .filter(db_models.ChatHistory.user_id == user.id)
        .order_by(db_models.ChatHistory.created_at.asc())
        .all()
    )
    filename = f"roastgpt-history-{datetime.now(timezone.utc).strftime('%Y%m%d')}.{format}"
    if format == "json":
        import json
        body = json.dumps(
            [
                {
                    "id": i.id,
                    "is_user": i.is_user,
                    "message": i.message,
                    "roast_response": i.roast_response,
                    "score_total": i.score_total,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                }
                for i in items
            ],
            indent=2,
            ensure_ascii=False,
        )
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    lines: list[str] = []
    if format == "md":
        lines.append(f"# RoastGPT chat history")
        lines.append(f"_Exported {datetime.now(timezone.utc).isoformat()}_\n")
        last_day = None
        for i in items:
            day = i.created_at.date().isoformat() if i.created_at else "?"
            if day != last_day:
                lines.append(f"\n## {day}\n")
                last_day = day
            who = "**You**" if i.is_user else "_RoastGPT_"
            lines.append(f"{who}: {i.message}")
            if i.roast_response and not i.is_user:
                lines.append(f"\n> {i.roast_response}\n")
        body = "\n".join(lines)
    else:
        for i in items:
            ts = i.created_at.isoformat() if i.created_at else ""
            if i.is_user:
                lines.append(f"[{ts}] You: {i.message}")
            else:
                lines.append(f"[{ts}] RoastGPT: {i.roast_response or i.message}")
                if i.score_total:
                    lines.append(f"  (score {i.score_total:.1f})")
            lines.append("")
        body = "\n".join(lines)
    media = "text/markdown" if format == "md" else "text/plain"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
