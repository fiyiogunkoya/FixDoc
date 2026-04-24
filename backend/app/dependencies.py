"""Composite dependencies that handle either Clerk JWT or API key auth.

Routes that are callable by both the web UI (Clerk) and the CLI (API key) use
`get_request_context` which returns a `(team_id, user_id)` tuple regardless of
the auth path taken.
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.auth import (
    _extract_bearer,
    hash_api_key,
    require_team_member,
    verify_clerk_jwt,
)
from app.models.api_key import ApiKey
from app.models.user import User


@dataclass
class RequestContext:
    team_id: uuid.UUID
    user_id: uuid.UUID
    auth_method: str  # "clerk" | "api_key"


def get_request_context(
    request: Request,
    team_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RequestContext:
    """Resolve team + user context via API key (CLI) or Clerk JWT (web UI)."""
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    if token.startswith(settings.api_key_prefix):
        api_key = (
            db.query(ApiKey).filter(ApiKey.hashed_token == hash_api_key(token)).one_or_none()
        )
        if api_key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown API key")
        return RequestContext(
            team_id=api_key.team_id,
            user_id=api_key.created_by_id,
            auth_method="api_key",
        )

    claims = verify_clerk_jwt(token, settings)
    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")
    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not provisioned")

    if team_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "team_id query parameter required"
        )
    require_team_member(team_id=str(team_id), user=user, db=db)
    return RequestContext(team_id=team_id, user_id=user.id, auth_method="clerk")
