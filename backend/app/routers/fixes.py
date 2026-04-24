"""Fix CRUD + search endpoints.

Auth works via either Clerk JWT (web UI) or API key (CLI) — see
`app.dependencies.get_request_context`.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import RequestContext, get_request_context
from app.schemas.common import PaginatedResponse
from app.schemas.fix import (
    FixBulkCreate,
    FixBulkResult,
    FixCreate,
    FixResponse,
    FixUpdate,
)
from app.services import fix_service

router = APIRouter(prefix="/api/v1/fixes", tags=["fixes"])


@router.get("", response_model=PaginatedResponse[FixResponse])
def list_fixes(
    ctx: RequestContext = Depends(get_request_context),
    project_id: Optional[uuid.UUID] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if q:
        rows = fix_service.search_fixes(db, team_id=ctx.team_id, q=q, limit=limit)
        return PaginatedResponse(items=rows, total=len(rows), limit=limit, offset=0)

    rows, total = fix_service.list_fixes(
        db, team_id=ctx.team_id, project_id=project_id, limit=limit, offset=offset
    )
    return PaginatedResponse(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=FixResponse, status_code=status.HTTP_201_CREATED)
def create_fix(
    payload: FixCreate,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    fix, _created = fix_service.create_fix(
        db, team_id=ctx.team_id, created_by_id=ctx.user_id, payload=payload
    )
    db.commit()
    return fix


@router.post("/bulk", response_model=FixBulkResult)
def bulk_create_fixes(
    payload: FixBulkCreate,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    return fix_service.bulk_create(
        db, team_id=ctx.team_id, created_by_id=ctx.user_id, items=payload.fixes
    )


@router.get("/{fix_id}", response_model=FixResponse)
def get_fix(
    fix_id: uuid.UUID,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    fix = fix_service.get_fix(db, team_id=ctx.team_id, fix_id=fix_id)
    if fix is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fix not found")
    return fix


@router.put("/{fix_id}", response_model=FixResponse)
def update_fix(
    fix_id: uuid.UUID,
    payload: FixUpdate,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    fix = fix_service.update_fix(
        db, team_id=ctx.team_id, fix_id=fix_id, payload=payload
    )
    if fix is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fix not found")
    return fix


@router.delete("/{fix_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fix(
    fix_id: uuid.UUID,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    ok = fix_service.delete_fix(db, team_id=ctx.team_id, fix_id=fix_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fix not found")
