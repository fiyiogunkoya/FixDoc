"""Webhook handlers — Clerk user lifecycle.

GitHub webhooks will land here too in Week 4 (handled in a separate PR).
"""
import hmac
import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_svix(payload: bytes, headers: dict, secret: str) -> bool:
    """Verify Clerk/Svix webhook signature.

    Clerk uses Svix-style headers: svix-id, svix-timestamp, svix-signature.
    Signature format: v1,<base64(hmac_sha256(secret, svix-id.svix-timestamp.payload))>
    """
    import base64

    if not secret:
        return False

    svix_id = headers.get("svix-id")
    svix_ts = headers.get("svix-timestamp")
    svix_sig = headers.get("svix-signature", "")
    if not (svix_id and svix_ts and svix_sig):
        return False

    # Secret is prefixed with "whsec_" — strip and base64-decode the remainder
    secret_bytes = base64.b64decode(secret.split("_", 1)[-1])
    to_sign = f"{svix_id}.{svix_ts}.{payload.decode('utf-8')}".encode()
    expected = base64.b64encode(
        hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    ).decode()

    for part in svix_sig.split(" "):
        version, _, candidate = part.partition(",")
        if version == "v1" and hmac.compare_digest(candidate, expected):
            return True
    return False


def _upsert_user(db: Session, data: dict[str, Any]) -> User:
    clerk_id = data.get("id")
    if not clerk_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing Clerk user id")

    emails = data.get("email_addresses") or []
    primary_email = ""
    for e in emails:
        if e.get("id") == data.get("primary_email_address_id"):
            primary_email = e.get("email_address", "")
            break
    if not primary_email and emails:
        primary_email = emails[0].get("email_address", "")

    display_name = " ".join(
        filter(None, [data.get("first_name"), data.get("last_name")])
    ).strip() or data.get("username") or primary_email

    existing = db.query(User).filter(User.clerk_user_id == clerk_id).one_or_none()
    if existing is not None:
        existing.email = primary_email or existing.email
        existing.display_name = display_name or existing.display_name
        db.commit()
        return existing

    user = User(clerk_user_id=clerk_id, email=primary_email, display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    payload = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if settings.clerk_webhook_secret and not _verify_svix(
        payload, headers, settings.clerk_webhook_secret
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON")

    event_type = event.get("type")
    data = event.get("data") or {}

    if event_type in ("user.created", "user.updated"):
        _upsert_user(db, data)
    elif event_type == "user.deleted":
        clerk_id = data.get("id")
        if clerk_id:
            db.query(User).filter(User.clerk_user_id == clerk_id).delete()
            db.commit()
