"""Change-impact analysis endpoint.

POST /api/v1/analyze
  - Accepts a Terraform plan JSON + optional DOT graph
  - Runs the `fixdoc.change_impact` engine scoped to the authenticated team
  - If a `pr` context is provided, posts/updates the PR comment via the
    team's installed GitHub App. Failures here become a `pr_comment_error`
    field in the 200 response — they don't fail the analysis.

The PR path requires a prior GitHub App install — see webhooks.py. The plain
analyze path works without any GitHub integration (CLI can hit it too).
"""
from __future__ import annotations

import logging
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.dependencies import RequestContext, get_request_context
from app.integrations.github_app import (
    get_installation_token_for_settings,
    upsert_pr_comment,
)
from app.models.github_installation import GitHubInstallation
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.services import analyze_service

from fixdoc.outcomes import compute_plan_fingerprint
from fixdoc.change_impact_format import FIXDOC_COMMENT_MARKER

logger = logging.getLogger("fixdoc.analyze")
router = APIRouter(prefix="/api/v1", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    payload: AnalyzeRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    analysis = analyze_service.run_terraform_analysis(
        db,
        team_id=ctx.team_id,
        plan=payload.plan,
        graph_dot=payload.graph_dot,
    )

    fingerprint: Optional[str] = None
    try:
        fingerprint = compute_plan_fingerprint(payload.plan)
    except Exception:
        # Fingerprinting is advisory; never let it fail the analysis itself.
        pass

    pr_comment_id: Optional[int] = None
    pr_comment_error: Optional[str] = None

    if payload.pr is not None:
        # Membership check is the one PR-side error worth a hard 4xx — it
        # protects against another team posting comments on a repo's PR
        # using a stranger's installation id.
        install = (
            db.query(GitHubInstallation)
            .filter(
                GitHubInstallation.installation_id == payload.pr.installation_id,
                GitHubInstallation.team_id == ctx.team_id,
            )
            .one_or_none()
        )
        if install is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "GitHub App installation is not linked to this team",
            )

        # Everything past this point is best-effort. Engine work succeeded;
        # PR-comment failures (bad token, GitHub API error, fake repo for
        # smoke tests) become a string in the 200 response body. We avoid
        # 5xx because Cloudflare replaces 5xx response bodies with its own
        # `error code: 502` template and the actual message gets lost.
        try:
            logger.info(
                "Analyze: posting PR comment install_id=%s repo=%s/%s pr=%d",
                payload.pr.installation_id,
                payload.pr.owner,
                payload.pr.repo,
                payload.pr.pull_number,
            )
            token = get_installation_token_for_settings(
                settings, payload.pr.installation_id
            )
            pr_comment_id = upsert_pr_comment(
                token,
                payload.pr.owner,
                payload.pr.repo,
                payload.pr.pull_number,
                analysis.markdown,
                FIXDOC_COMMENT_MARKER,
            )
            logger.info("Analyze: PR comment posted id=%s", pr_comment_id)
        except BaseException as exc:
            tb = traceback.format_exc()
            logger.error("Analyze: PR comment failed:\n%s", tb)
            pr_comment_error = f"{type(exc).__name__}: {exc}"

    return AnalyzeResponse(
        score=analysis.result.score,
        severity=analysis.result.severity,
        plan_fingerprint=fingerprint,
        markdown=analysis.markdown,
        affected=analysis.result.affected or [],
        relevant_fixes=analysis.result.relevant_fixes or [],
        contextual_checks=analysis.result.contextual_checks or [],
        pr_comment_id=pr_comment_id,
        pr_comment_error=pr_comment_error,
    )
