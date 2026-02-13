"""Blast radius command for fixdoc CLI."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import click

from ..blast_radius import BlastResult, analyze_blast_radius
from ..storage import FixRepository


def _format_human(result: BlastResult) -> str:
    """Format blast radius result for human-readable terminal output."""
    lines = []

    # Header
    lines.append("Blast Radius Analysis")
    lines.append("=" * 21)

    # Score and severity
    sev = result.severity.upper()
    sev_colors = {
        "CRITICAL": "red",
        "HIGH": "yellow",
        "MEDIUM": "cyan",
        "LOW": "green",
    }
    color = sev_colors.get(sev, "white")
    score_line = f"Score: {result.score} / 100  [{sev}]"
    lines.append(click.style(score_line, fg=color))
    lines.append("")

    # Changed control points
    if result.control_points:
        lines.append(f"Changed Control Points ({len(result.control_points)}):")
        for cp in result.control_points:
            action = cp["action"].upper()
            addr = cp["address"]
            cat = cp["category"]
            crit = cp["criticality"]
            lines.append(f"  {action:<8}{addr:<40}[{cat}, criticality: {crit}]")
        lines.append("")

    # Affected resources
    if result.affected:
        count = len(result.affected)
        display_limit = 10
        lines.append(f"Affected Resources ({count}):")
        for ar in result.affected[:display_limit]:
            addr = ar["address"]
            depth = ar["depth"]
            via = ar["path"][0] if ar["path"] else "?"
            lines.append(f"  {addr:<40}(depth: {depth}, via: {via})")
        if count > display_limit:
            lines.append(f"  ... and {count - display_limit} more")
        lines.append("")

    # History matches
    if result.history_matches:
        lines.append(f"Fix History Matches ({len(result.history_matches)}):")
        for hm in result.history_matches:
            fix_id = hm["id"]
            issue = hm["issue"]
            issue_preview = issue[:60] + "..." if len(issue) > 60 else issue
            lines.append(f"  FIX-{fix_id}: {issue_preview}")
        lines.append("")

    # Recommended checks
    if result.checks:
        lines.append("Recommended Checks:")
        for check in result.checks:
            lines.append(f"  - {check}")
        lines.append("")

    # Summary
    ps = result.plan_summary
    lines.append(
        f"Summary: {ps.get('total_changes', 0)} changes, "
        f"{ps.get('control_points', 0)} control points, "
        f"{ps.get('affected_resources', 0)} affected resources"
    )

    return "\n".join(lines)


def _format_json(result: BlastResult) -> str:
    """Format blast radius result as JSON."""
    data = {
        "analysis_id": result.analysis_id,
        "timestamp": result.timestamp,
        "score": result.score,
        "severity": result.severity,
        "changes": result.changes,
        "control_points": result.control_points,
        "affected": result.affected,
        "why_paths": result.why_paths,
        "checks": result.checks,
        "history_matches": result.history_matches,
        "plan_summary": result.plan_summary,
    }
    return json.dumps(data, indent=2)


def _auto_run_terraform_graph() -> Optional[str]:
    """Try to run `terraform graph` if terraform is on PATH.

    Returns DOT text or None.
    """
    if not shutil.which("terraform"):
        return None
    try:
        proc = subprocess.run(
            ["terraform", "graph"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


@click.command("blast-radius")
@click.argument("plan_file", type=click.Path(exists=True))
@click.option(
    "--graph",
    "-g",
    "graph_file",
    type=click.Path(exists=True),
    default=None,
    help="Path to DOT file from `terraform graph`. Auto-runs if terraform is on PATH.",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["human", "json"]),
    default="human",
    help="Output format.",
)
@click.option(
    "--max-depth",
    "-d",
    type=int,
    default=5,
    help="Max BFS traversal depth for propagation.",
)
@click.pass_context
def blast_radius(
    ctx, plan_file: str, graph_file: Optional[str],
    output_format: str, max_depth: int,
):
    """Estimate the blast radius of infrastructure changes.

    \b
    Usage:
        terraform show -json plan.tfplan > plan.json
        fixdoc blast-radius plan.json
        fixdoc blast-radius plan.json --graph graph.dot
        fixdoc blast-radius plan.json --format json

    \b
    Options:
        --graph/-g      Path to DOT file from `terraform graph`
        --format/-f     Output format: human or json
        --max-depth/-d  Max BFS traversal depth (default: 5)
    """
    repo = FixRepository(ctx.obj["base_path"])
    plan_path = Path(plan_file)

    try:
        with open(plan_path, "r") as f:
            plan = json.load(f)
    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON in plan file.", err=True)
        click.echo(
            "Hint: Use `terraform show -json plan.tfplan > plan.json`",
            err=True,
        )
        raise SystemExit(1)

    # Get graph DOT text
    dot_text = None
    if graph_file:
        with open(graph_file, "r") as f:
            dot_text = f.read()
    else:
        dot_text = _auto_run_terraform_graph()
        if dot_text is None:
            click.echo(
                "Note: terraform not on PATH; running without dependency graph.",
                err=True,
            )

    result = analyze_blast_radius(plan, repo, dot_text=dot_text, max_depth=max_depth)

    if output_format == "json":
        click.echo(_format_json(result))
    else:
        click.echo(_format_human(result))
