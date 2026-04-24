"""Integration-binding endpoints — tie external resources (GitHub installs,
Slack workspaces in Phase 1) to the acting team.

The GitHub install flow: user clicks "Connect GitHub" in the web UI → we open
GitHub's install URL with `state=<team_id>` → GitHub redirects back with
`installation_id` + `state` → the frontend POSTs here to persist the link.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import RequestContext, get_request_context
from app.models.github_installation import GitHubInstallation

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


class GitHubLinkRequest(BaseModel):
    installation_id: int


class GitHubInstallationResponse(BaseModel):
    model_config = {"from_attributes": True}

    installation_id: int
    repositories: list


@router.get("/github", response_model=List[GitHubInstallationResponse])
def list_installations(
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    return (
        db.query(GitHubInstallation)
        .filter(GitHubInstallation.team_id == ctx.team_id)
        .all()
    )


@router.post("/github", response_model=GitHubInstallationResponse)
def link_github_installation(
    payload: GitHubLinkRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """Bind a GitHub App installation ID to the caller's team.

    This is idempotent — if the installation is already linked to this team we
    no-op; if it's linked to a DIFFERENT team we refuse (prevents theft).
    """
    row = (
        db.query(GitHubInstallation)
        .filter(GitHubInstallation.installation_id == payload.installation_id)
        .one_or_none()
    )
    if row is not None:
        if row.team_id != ctx.team_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Installation is linked to a different team",
            )
        return row

    row = GitHubInstallation(
        installation_id=payload.installation_id,
        team_id=ctx.team_id,
        repositories=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/github/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_github_installation(
    installation_id: int,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    row = (
        db.query(GitHubInstallation)
        .filter(
            GitHubInstallation.installation_id == installation_id,
            GitHubInstallation.team_id == ctx.team_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Installation not found")
    db.delete(row)
    db.commit()
