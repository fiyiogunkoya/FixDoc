"""Clerk-authenticated user endpoints + API key management."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.auth import _extract_bearer, get_current_user, hash_api_key
from app.models.api_key import ApiKey
from app.models.team import Team
from app.models.user import User
from app.schemas.team import ApiKeyCreate, ApiKeyResponse, ApiKeyWithToken
from app.schemas.user import UserResponse
from app.services import api_key_service

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/auth/cli-whoami")
def cli_whoami(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Resolve team context for an API key — used by `fixdoc login`.

    Unlike `/auth/me` (Clerk-only), this accepts `fd_live_...` tokens and
    returns the team_id, team_slug, and token name so the CLI can persist
    them to `~/.fixdoc/cloud.yaml`.
    """
    token = _extract_bearer(request)
    if not token or not token.startswith(settings.api_key_prefix):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key required")

    hashed = hash_api_key(token)
    api_key = db.query(ApiKey).filter(ApiKey.hashed_token == hashed).one_or_none()
    if api_key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown API key")

    team = db.query(Team).filter(Team.id == api_key.team_id).one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")

    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "team_id": str(team.id),
        "team_slug": team.slug,
        "team_name": team.name,
        "api_key_name": api_key.name,
        "api_key_id": str(api_key.id),
    }


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    team_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # ensure membership
    from app.middleware.auth import require_team_member

    require_team_member(team_id=team_id, user=user, db=db)
    from app.models.api_key import ApiKey

    return (
        db.query(ApiKey)
        .filter(ApiKey.team_id == team_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.post("/api-keys", response_model=ApiKeyWithToken, status_code=status.HTTP_201_CREATED)
def create_api_key(
    team_id: str,
    payload: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.middleware.auth import require_team_member

    require_team_member(team_id=team_id, user=user, db=db)

    row, token = api_key_service.create_api_key(
        db, team_id=team_id, user_id=user.id, name=payload.name
    )
    return ApiKeyWithToken(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        token=token,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.api_key import ApiKey
    from app.middleware.auth import require_team_member

    row = db.query(ApiKey).filter(ApiKey.id == key_id).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    require_team_member(team_id=str(row.team_id), user=user, db=db)
    db.delete(row)
    db.commit()
