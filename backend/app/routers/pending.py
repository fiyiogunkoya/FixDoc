"""Pending entry endpoints — bulk upsert from CLI + resolve."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import RequestContext, get_request_context
from app.models.pending_entry import PendingEntry
from app.schemas.pending import (
    PendingBulkCreate,
    PendingEntryCreate,
    PendingEntryResponse,
)

router = APIRouter(prefix="/api/v1/pending", tags=["pending"])


def _apply_entry(
    db: Session,
    *,
    team_id: uuid.UUID,
    created_by_id: uuid.UUID,
    payload: PendingEntryCreate,
) -> PendingEntry:
    existing = (
        db.query(PendingEntry)
        .filter(
            PendingEntry.team_id == team_id,
            PendingEntry.error_id == payload.error_id,
        )
        .one_or_none()
    )
    if existing is not None:
        for field in (
            "short_message",
            "error_excerpt",
            "tags",
            "resource_address",
            "error_code",
            "file",
            "command",
            "cwd",
            "session_id",
            "status",
            "command_family",
            "kind",
            "worthiness",
        ):
            setattr(existing, field, getattr(payload, field))
        return existing

    row = PendingEntry(
        team_id=team_id,
        project_id=payload.project_id,
        created_by_id=created_by_id,
        **payload.model_dump(exclude={"project_id"}),
    )
    db.add(row)
    return row


@router.get("", response_model=List[PendingEntryResponse])
def list_pending(
    ctx: RequestContext = Depends(get_request_context),
    project_id: Optional[uuid.UUID] = Query(None),
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = db.query(PendingEntry).filter(PendingEntry.team_id == ctx.team_id)
    if project_id is not None:
        query = query.filter(PendingEntry.project_id == project_id)
    if not include_resolved:
        query = query.filter(PendingEntry.status == "pending")
    return query.order_by(PendingEntry.created_at.desc()).all()


@router.post("", response_model=List[PendingEntryResponse], status_code=status.HTTP_201_CREATED)
def bulk_upsert_pending(
    payload: PendingBulkCreate,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = [
        _apply_entry(db, team_id=ctx.team_id, created_by_id=ctx.user_id, payload=entry)
        for entry in payload.entries
    ]
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.post("/{entry_id}/resolve", response_model=PendingEntryResponse)
def resolve_pending(
    entry_id: uuid.UUID,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    row = (
        db.query(PendingEntry)
        .filter(PendingEntry.team_id == ctx.team_id, PendingEntry.id == entry_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pending entry not found")
    row.status = "resolved"
    db.commit()
    db.refresh(row)
    return row
