"""Change-impact analysis service.

Thin wrapper around `fixdoc.change_impact.analyze_change_impact` — the engine
itself is unchanged, shared verbatim with the CLI. Backend-specific bits:
  - Converts team's DB fixes into in-memory `Fix` objects for the matcher
  - Calls `_redact_sensitive_values` on the plan before storage
  - Returns both the engine `ImpactResult` and a PR-ready markdown string
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fixdoc.change_impact import (
    ImpactResult,
    analyze_change_impact,
)
from fixdoc.change_impact_format import format_impact_pr_comment
from fixdoc.models import Fix as CliFix
from sqlalchemy.orm import Session

from app.models.fix import Fix as FixModel


def _team_fixes_as_objects(db: Session, team_id: uuid.UUID) -> List[CliFix]:
    """Hydrate team fixes into CLI `Fix` dataclasses for the relevance engine."""
    rows = db.query(FixModel).filter(FixModel.team_id == team_id).all()
    out: List[CliFix] = []
    for r in rows:
        out.append(
            CliFix(
                issue=r.issue,
                resolution=r.resolution,
                error_excerpt=r.error_excerpt,
                tags=",".join(r.tags) if r.tags else None,
                notes=r.notes,
                id=str(r.id),
                created_at=r.created_at.isoformat() if r.created_at else "",
                updated_at=r.updated_at.isoformat() if r.updated_at else "",
                author=r.author,
                author_email=r.author_email,
                is_private=r.is_private,
                source_error_ids=r.source_error_ids,
                applied_count=r.applied_count,
                success_count=r.success_count,
                last_applied_at=(
                    r.last_applied_at.isoformat() if r.last_applied_at else None
                ),
                memory_type=r.memory_type,
                content_hash=r.content_hash,
            )
        )
    return out


@dataclass
class AnalysisResult:
    result: ImpactResult
    markdown: str


class _InMemoryRepo:
    """Adapter shaped like `fixdoc.storage.FixRepository` for the change_impact
    engine — which only calls `.list_all()`."""

    def __init__(self, fixes: List[CliFix]) -> None:
        self._fixes = fixes

    def list_all(self) -> List[CliFix]:
        return self._fixes


def run_terraform_analysis(
    db: Session,
    *,
    team_id: uuid.UUID,
    plan: Dict[str, Any],
    graph_dot: Optional[str] = None,
) -> AnalysisResult:
    """Run change impact against team fixes and return engine + markdown."""
    repo = _InMemoryRepo(_team_fixes_as_objects(db, team_id))
    impact = analyze_change_impact(plan, repo, dot_text=graph_dot)
    return AnalysisResult(result=impact, markdown=format_impact_pr_comment(impact))
