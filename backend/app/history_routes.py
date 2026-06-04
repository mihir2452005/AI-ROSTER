"""Chat history routes - users can view their past conversations.

Chat history is persisted when a user is authenticated. Anonymous sessions
continue to work but their history is not persisted across server restarts.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import auth, auth_schemas, db_models
from .database import get_db

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=auth_schemas.ChatHistoryResponse)
def my_history(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> auth_schemas.ChatHistoryResponse:
    """Return the authenticated user's chat history, newest first."""
    total = db.query(func.count(db_models.ChatHistory.id)).filter(
        db_models.ChatHistory.user_id == user.id
    ).scalar() or 0

    items = db.query(db_models.ChatHistory).filter(
        db_models.ChatHistory.user_id == user.id
    ).order_by(db_models.ChatHistory.created_at.desc()).offset(skip).limit(limit).all()

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
