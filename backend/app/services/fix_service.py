"""Fix service — persistence + content-hash dedup.

Reuses `fixdoc.models.compute_content_hash` so the CLI and backend hash
identically — a fix pushed from CLI dedups against a fix created via web UI
and vice versa.
"""
import uuid
from typing import List, Optional, Tuple

from fixdoc.models import compute_content_hash
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.fix import Fix as FixModel
from app.schemas.fix import FixBulkResult, FixCreate, FixUpdate


def _parse_tags(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    return tags or None


def create_fix(
    db: Session,
    *,
    team_id: uuid.UUID,
    created_by_id: uuid.UUID,
    payload: FixCreate,
) -> Tuple[FixModel, bool]:
    """Create a fix, or return the existing one on content_hash collision.

    Returns (fix, created_bool). `created=False` means a duplicate was detected.
    """
    content_hash = payload.content_hash or compute_content_hash(
        payload.issue, payload.resolution
    )

    existing = (
        db.query(FixModel)
        .filter(FixModel.team_id == team_id, FixModel.content_hash == content_hash)
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    fix = FixModel(
        team_id=team_id,
        project_id=payload.project_id,
        created_by_id=created_by_id,
        content_hash=content_hash,
        issue=payload.issue,
        resolution=payload.resolution,
        error_excerpt=payload.error_excerpt,
        tags=_parse_tags(payload.tags),
        notes=payload.notes,
        author=payload.author,
        author_email=payload.author_email,
        is_private=payload.is_private,
        source_error_ids=payload.source_error_ids,
        memory_type=payload.memory_type,
    )
    db.add(fix)
    db.flush()
    return fix, True


def bulk_create(
    db: Session,
    *,
    team_id: uuid.UUID,
    created_by_id: uuid.UUID,
    items: List[FixCreate],
) -> FixBulkResult:
    created = 0
    duplicates = 0
    ids: List[uuid.UUID] = []
    for payload in items:
        fix, was_created = create_fix(
            db, team_id=team_id, created_by_id=created_by_id, payload=payload
        )
        if was_created:
            created += 1
        else:
            duplicates += 1
        ids.append(fix.id)
    db.commit()
    return FixBulkResult(created=created, duplicates=duplicates, ids=ids)


def list_fixes(
    db: Session,
    *,
    team_id: uuid.UUID,
    project_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[FixModel], int]:
    query = db.query(FixModel).filter(FixModel.team_id == team_id)
    if project_id is not None:
        query = query.filter(FixModel.project_id == project_id)
    total = query.count()
    rows = (
        query.order_by(FixModel.updated_at.desc()).limit(limit).offset(offset).all()
    )
    return rows, total


def search_fixes(
    db: Session,
    *,
    team_id: uuid.UUID,
    q: str,
    limit: int = 50,
) -> List[FixModel]:
    """Naive ILIKE search — good enough for Phase 0.

    Phase 1+ swap in pgvector or Typesense for semantic retrieval.
    """
    pattern = f"%{q}%"
    return (
        db.query(FixModel)
        .filter(
            FixModel.team_id == team_id,
            or_(
                FixModel.issue.ilike(pattern),
                FixModel.resolution.ilike(pattern),
                FixModel.error_excerpt.ilike(pattern),
                FixModel.notes.ilike(pattern),
            ),
        )
        .order_by(FixModel.updated_at.desc())
        .limit(limit)
        .all()
    )


def get_fix(db: Session, *, team_id: uuid.UUID, fix_id: uuid.UUID) -> Optional[FixModel]:
    return (
        db.query(FixModel)
        .filter(FixModel.team_id == team_id, FixModel.id == fix_id)
        .one_or_none()
    )


def update_fix(
    db: Session,
    *,
    team_id: uuid.UUID,
    fix_id: uuid.UUID,
    payload: FixUpdate,
) -> Optional[FixModel]:
    fix = get_fix(db, team_id=team_id, fix_id=fix_id)
    if fix is None:
        return None

    data = payload.model_dump(exclude_unset=True)
    if "tags" in data:
        data["tags"] = _parse_tags(data["tags"])
    for key, value in data.items():
        setattr(fix, key, value)

    if "issue" in data or "resolution" in data:
        fix.content_hash = compute_content_hash(fix.issue, fix.resolution)

    db.commit()
    db.refresh(fix)
    return fix


def delete_fix(db: Session, *, team_id: uuid.UUID, fix_id: uuid.UUID) -> bool:
    fix = get_fix(db, team_id=team_id, fix_id=fix_id)
    if fix is None:
        return False
    db.delete(fix)
    db.commit()
    return True
