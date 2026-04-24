"""Clerk JWT verification + API key validation.

Two authentication paths:
  1. Clerk session JWT (web UI) — verified against Clerk's JWKS endpoint
  2. API key (CLI) — hashed lookup in api_keys table, `fd_live_...` prefix

Request handlers use `get_current_user()` (Clerk) or `get_api_key_team()` (CLI).
"""
import hashlib
import time
from typing import Any, Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.team import TeamMember
from app.models.user import User


class _JWKSCache:
    """Tiny in-process JWKS cache — Clerk rotates keys infrequently."""

    def __init__(self) -> None:
        self._client: Optional[PyJWKClient] = None
        self._url: Optional[str] = None

    def get_client(self, jwks_url: str) -> PyJWKClient:
        if self._client is None or self._url != jwks_url:
            self._client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
            self._url = jwks_url
        return self._client


_jwks_cache = _JWKSCache()


def verify_clerk_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Verify a Clerk-issued JWT against Clerk's JWKS.

    Returns the decoded claims dict. Raises HTTPException(401) on failure.
    """
    if not settings.clerk_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clerk JWKS URL not configured",
        )
    try:
        jwks_client = _jwks_cache.get_client(settings.clerk_jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}")

    if claims.get("iss", "").rstrip("/").split("/")[-1] and claims.get("exp", 0) < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")

    return claims


def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1].strip()


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Resolve the current user via Clerk JWT.

    Does NOT accept API keys — those are team-scoped and use `get_api_key_team()`.
    """
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    claims = verify_clerk_jwt(token, settings)
    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")

    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "User not provisioned yet — Clerk webhook may not have fired",
        )
    return user


def get_api_key_team(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ApiKey:
    """Resolve a team-scoped API key from the Authorization header.

    CLI authenticates with `Authorization: Bearer fd_live_XXXXXX`.
    Raises 401 if the token is missing, not an API key, or unknown.
    """
    token = _extract_bearer(request)
    if not token or not token.startswith(settings.api_key_prefix):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key required")

    hashed = hash_api_key(token)
    api_key = db.query(ApiKey).filter(ApiKey.hashed_token == hashed).one_or_none()
    if api_key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown API key")
    return api_key


def require_team_member(
    team_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMember:
    """Enforce that `user` is a member of `team_id`. Returns the membership row."""
    member = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user.id)
        .one_or_none()
    )
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this team")
    return member


async def fetch_clerk_jwks_once(settings: Settings) -> None:
    """Optional startup hook: warm the JWKS cache."""
    if not settings.clerk_jwks_url:
        return
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.get(settings.clerk_jwks_url)
        except httpx.HTTPError:
            pass
