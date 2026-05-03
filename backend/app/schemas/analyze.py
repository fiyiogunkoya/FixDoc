"""Analyze endpoint schemas."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PRContext(BaseModel):
    """Identifies a PR so the backend can post a comment via the GitHub App."""

    installation_id: int
    owner: str = Field(..., min_length=1, max_length=128)
    repo: str = Field(..., min_length=1, max_length=128)
    pull_number: int = Field(..., gt=0)
    commit_sha: Optional[str] = None


class AnalyzeRequest(BaseModel):
    plan: Dict[str, Any] = Field(..., description="Terraform `plan -out=x && show -json x` JSON")
    graph_dot: Optional[str] = Field(None, description="Optional `terraform graph` DOT output")
    pr: Optional[PRContext] = Field(
        None, description="If provided, backend posts a PR comment via the GitHub App"
    )


class AnalyzeResponse(BaseModel):
    score: float
    severity: str
    plan_fingerprint: Optional[str] = None
    markdown: str
    affected: List[Dict[str, Any]] = []
    relevant_fixes: List[Dict[str, Any]] = []
    contextual_checks: List[Dict[str, Any]] = []
    pr_comment_id: Optional[int] = None
    # When the analysis itself succeeds but the PR comment can't be posted
    # (bad installation token, GitHub API error, fake repo for testing),
    # we still return 200 with the analysis result and surface the failure
    # here. Returning 5xx makes Cloudflare replace our JSON body with its
    # own bare "error code: 502" template, hiding the real cause.
    pr_comment_error: Optional[str] = None
