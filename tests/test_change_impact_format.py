"""Smoke tests for the shared markdown formatter."""
from fixdoc.change_impact import ImpactResult
from fixdoc.change_impact_format import (
    FIXDOC_COMMENT_MARKER,
    SEVERITY_EMOJI,
    format_impact_markdown,
    format_impact_pr_comment,
)


def _result(score=42.0, severity="medium", **extra):
    defaults = dict(
        score=score,
        severity=severity,
        changes=[],
        affected=[],
        control_points=[],
        why_paths=[],
        checks=[],
        contextual_checks=[],
        plan_summary={
            "total_changes": 3,
            "by_action": {"create": 1, "update": 2, "delete": 0, "replace": 0},
            "control_points": 1,
            "affected_resources": 2,
        },
        history_matches=[],
        resource_warnings=[],
        relevant_fixes=[],
        score_explanation=[
            {"label": "IAM trust boundary change", "delta": 20, "kind": "iam"},
            {"label": "modifier: suppressed", "delta": 0, "kind": "modifier"},
        ],
        outcome_matches=[],
    )
    defaults.update(extra)
    return ImpactResult(**defaults)


def test_markdown_contains_score_and_severity():
    md = format_impact_markdown(_result(82, "high"))
    assert "82/100" in md
    assert "**HIGH**" in md
    assert SEVERITY_EMOJI["high"] in md


def test_markdown_summary_table():
    md = format_impact_markdown(_result())
    assert "| Total changes | 3 |" in md
    assert "| Creates | 1 |" in md


def test_modifier_kind_is_hidden_from_score_explanation():
    md = format_impact_markdown(_result())
    assert "IAM trust boundary change" in md
    assert "modifier: suppressed" not in md


def test_pr_comment_prepends_marker():
    md = format_impact_pr_comment(_result())
    assert md.startswith(FIXDOC_COMMENT_MARKER)
    assert "Terraform Risk Analysis" in md


def test_outcome_matches_rendered_when_present():
    om = [
        {
            "outcome_id": "abc12345",
            "applied_at": "2026-02-01T10:00:00Z",
            "apply_error_codes": ["AccessDenied", "LimitExceeded"],
        }
    ]
    md = format_impact_markdown(_result(outcome_matches=om))
    assert "Historical Apply Outcomes" in md
    assert "AccessDenied" in md
    assert "abc12345" in md
