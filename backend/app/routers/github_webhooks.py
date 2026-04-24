"""GitHub App webhook handler.

Currently handles:
  - `installation` (created|deleted)         — create/drop GitHubInstallation row
  - `installation_repositories` (added|removed) — update `repositories` list
  - `ping`                                   — smoke test, returns 200

PR analysis is triggered by the customer's workflow calling `POST /api/v1/analyze`
with a `pr` block — NOT by `pull_request` webhook events. This avoids running
terraform inside our infra (which would require handling customer cloud creds).
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.integrations.github_app import verify_webhook_signature
from app.models.github_installation import GitHubInstallation

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _repo_summary(repo: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the fields we actually use for presentation/audit."""
    return {
        "id": repo.get("id"),
        "full_name": repo.get("full_name"),
        "private": repo.get("private"),
    }


@router.post("/github", status_code=status.HTTP_204_NO_CONTENT)
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256")

    # In dev the webhook secret may be empty — only skip verification when
    # explicitly unconfigured AND not production.
    if settings.github_webhook_secret:
        if not verify_webhook_signature(body, signature, settings.github_webhook_secret):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    elif settings.environment == "production":
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Webhook secret not configured",
        )

    event = request.headers.get("x-github-event")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON")

    if event == "ping":
        return

    if event == "installation":
        action = payload.get("action")
        install_id = payload.get("installation", {}).get("id")
        repos = [_repo_summary(r) for r in payload.get("repositories", [])]

        if action == "created" and install_id:
            # We don't yet know which team this belongs to — the user must click
            # "Connect" in the web UI, which opens GitHub's install flow with a
            # state= that we'll decode post-callback in Phase 1a. For Phase 0
            # we store the row orphaned (team_id=null not allowed, so we stash
            # it in a temporary claim table — KEEPING SIMPLE: reject if no
            # state could be mapped. See NEXT LEVEL note at bottom.)
            # For now we'll accept and assume the install was triggered via
            # our flow; the /integrations/link endpoint binds it to a team.
            existing = (
                db.query(GitHubInstallation)
                .filter(GitHubInstallation.installation_id == install_id)
                .one_or_none()
            )
            if existing is not None:
                existing.repositories = repos
                db.commit()
        elif action == "deleted" and install_id:
            db.query(GitHubInstallation).filter(
                GitHubInstallation.installation_id == install_id
            ).delete()
            db.commit()
        return

    if event == "installation_repositories":
        install_id = payload.get("installation", {}).get("id")
        if install_id is None:
            return
        row = (
            db.query(GitHubInstallation)
            .filter(GitHubInstallation.installation_id == install_id)
            .one_or_none()
        )
        if row is None:
            return
        added = [_repo_summary(r) for r in payload.get("repositories_added", [])]
        removed_ids = {r.get("id") for r in payload.get("repositories_removed", [])}
        current = [r for r in (row.repositories or []) if r.get("id") not in removed_ids]
        current.extend(added)
        row.repositories = current
        db.commit()
        return

    # Any other event — just 204, we don't care yet
