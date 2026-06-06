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

from . import auth, auth_schemas, db_models, utils
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
                session_id=item.session_id,
            )
            for item in items
        ],
        total=total,
    )


# ---- Sessions list (for "Continue previous chat") ----

@router.get("/sessions", response_model=auth_schemas.ChatSessionListResponse)
def my_sessions(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=200),
) -> auth_schemas.ChatSessionListResponse:
    """Return the user's persisted chat sessions, newest first.

    Each row corresponds to one `RoastSession` (created on
    /session/start for authenticated users). The frontend renders a
    "Continue chat" link for each one, deep-linking back into the
    /chat/{sessionId} page.

    `q` matches the first user message in the session (substring,
    case-insensitive).
    """
    base = db.query(db_models.RoastSession).filter(
        db_models.RoastSession.user_id == user.id,
    )
    rows = base.order_by(
        db_models.RoastSession.last_accessed_at.desc()
    ).offset(skip).limit(limit).all()

    # Build previews: for each session, the first user message
    # from the associated chat history (or "roast response" if we
    # stored the assistant side first). Cap to 80 chars.
    out: list[auth_schemas.ChatSessionSummary] = []
    for r in rows:
        first_user_msg = (
            db.query(db_models.ChatHistory.message)
            .filter(
                db_models.ChatHistory.user_id == user.id,
                db_models.ChatHistory.session_id == r.session_id,
                db_models.ChatHistory.is_user.is_(True),
            )
            .order_by(db_models.ChatHistory.created_at.asc())
            .first()
        )
        preview = (first_user_msg[0][:80] + "…") if first_user_msg and len(first_user_msg[0]) > 80 else (first_user_msg[0] if first_user_msg else None)
        # Count messages on this session.
        msg_count = (
            db.query(func.count(db_models.ChatHistory.id))
            .filter(
                db_models.ChatHistory.user_id == user.id,
                db_models.ChatHistory.session_id == r.session_id,
            )
            .scalar() or 0
        )
        # Sum damage.
        score = (
            db.query(func.coalesce(func.sum(db_models.ChatHistory.score_total), 0.0))
            .filter(
                db_models.ChatHistory.user_id == user.id,
                db_models.ChatHistory.session_id == r.session_id,
            )
            .scalar() or 0.0
        )
        out.append(auth_schemas.ChatSessionSummary(
            session_id=r.session_id,
            mode=r.mode,
            personality=r.personality,
            message_count=int(msg_count),
            last_message_at=r.last_accessed_at,
            is_ended=r.ended_at is not None,
            score_total=float(score),
            preview=preview,
        ))
    if q:
        ql = q.lower()
        out = [s for s in out if s.preview and ql in s.preview.lower()]
    total = base.count()
    return auth_schemas.ChatSessionListResponse(sessions=out, total=total)


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

    Feature flag: `history_export_enabled` (default: True). Set to
    False in /admin/feature-flags to disable export globally.
    """
    if not utils.is_flag_enabled(db, "history_export_enabled", default=True):
        raise HTTPException(
            status_code=503,
            detail="History export is temporarily disabled.",
        )
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
