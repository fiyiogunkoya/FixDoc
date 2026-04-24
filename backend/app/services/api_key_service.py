"""API key issuance — `fd_live_<32hex>` tokens with sha256-hashed storage."""
import secrets
import uuid
from typing import Tuple

from sqlalchemy.orm import Session

from app.config import get_settings
from app.middleware.auth import hash_api_key
from app.models.api_key import ApiKey


def generate_token() -> Tuple[str, str]:
    """Return (full_token, prefix)."""
    settings = get_settings()
    suffix = secrets.token_hex(16)  # 32 hex chars
    token = f"{settings.api_key_prefix}{suffix}"
    return token, settings.api_key_prefix.rstrip("_")


def create_api_key(
    db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, name: str
) -> Tuple[ApiKey, str]:
    """Create an API key row; returns (row, plaintext_token).

    The plaintext token is only returned at creation; subsequent reads only
    expose the prefix for identification.
    """
    token, prefix = generate_token()
    row = ApiKey(
        team_id=team_id,
        created_by_id=user_id,
        name=name,
        hashed_token=hash_api_key(token),
        prefix=prefix,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, token
