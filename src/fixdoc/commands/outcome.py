"""Outcome commands for fixdoc CLI.

Record apply results, list and inspect outcomes.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from ..outcomes import Outcome, OutcomeStore, compute_plan_fingerprint


@click.group()
def outcome():
    """Manage apply outcome records."""
    pass


@outcome.command("record-apply")
@click.option(
    "--fingerprint",
    "fingerprint",
    default=None,
    help="Plan fingerprint from the analysis step (preferred).",
)
@click.option(
    "--plan",
    "plan_file",
    type=click.Path(exists=True),
    default=None,
    help="Compute fingerprint from plan file (fallback).",
)
@click.option(
    "--result",
    "apply_result",
    type=click.Choice(["success", "failure"]),
    required=True,
    help="Apply result: success or failure.",
)
@click.option(
    "--error-output",
    "error_output",
    default=None,
    help="Error text on failure.",
)
@click.option(
    "--error-file",
    "error_file",
    type=click.Path(exists=True),
    default=None,
    help="Read error text from file.",
)
@click.option(
    "--commit",
    "commit_sha",
    default=None,
    help="Commit SHA of the apply.",
)
def record_apply(
    fingerprint: Optional[str],
    plan_file: Optional[str],
    apply_result: str,
    error_output: Optional[str],
    error_file: Optional[str],
    commit_sha: Optional[str],
):
    """Record the apply result, linking to a prior analysis.

    \b
    Usage:
        fixdoc outcome record-apply --fingerprint <fp> --result success
        fixdoc outcome record-apply --plan plan.json --result failure
        echo "Error: ..." | fixdoc outcome record-apply --fp <fp> --result failure
    """
    # Resolve fingerprint
    fp = fingerprint
    if fp is None and plan_file is not None:
        with open(plan_file, "r") as f:
            plan = json.load(f)
        fp = compute_plan_fingerprint(plan)

    # Resolve error text
    err_text = error_output
    if err_text is None and error_file is not None:
        err_text = Path(error_file).read_text(encoding="utf-8", errors="replace")
    if err_text is None and not sys.stdin.isatty():
        err_text = sys.stdin.read()
    if err_text is not None:
        err_text = err_text[:2000]

    # Extract error codes from error text
    error_codes = []
    if err_text and apply_result == "failure":
        import re

        for m in re.finditer(r"Error:\s+(\S+)", err_text):
            code = m.group(1).rstrip(",.:;")
            if code and code not in error_codes:
                error_codes.append(code)

    store = OutcomeStore()

    # Try to link to existing analyzed outcome
    if fp:
        matches = store.find_by_fingerprint(fp)
        analyzed = [o for o in matches if o.status == "analyzed"]
        if analyzed:
            # Update the most recent analyzed outcome
            target = analyzed[-1]
            store.update_apply_result(
                target.outcome_id,
                apply_result,
                error_output=err_text,
                error_codes=error_codes,
                commit_sha=commit_sha,
            )
            click.echo(
                f"Linked apply result to outcome {target.outcome_id} "
                f"(fingerprint: {fp[:12]}...)"
            )
            return

    # Create standalone outcome
    oc = Outcome(
        plan_fingerprint=fp or "",
        apply_result=apply_result,
        apply_error_output=err_text,
        apply_error_codes=error_codes,
        apply_commit_sha=commit_sha,
        link_type="none",
        status="applied",
        applied_at=datetime.now(timezone.utc).isoformat(),
    )
    store.save(oc)
    click.echo(f"Recorded standalone apply outcome {oc.outcome_id} [unlinked]")


@outcome.command("list")
@click.option(
    "--status",
    "filter_status",
    type=click.Choice(["analyzed", "applied"]),
    default=None,
    help="Filter by status.",
)
@click.option(
    "--limit",
    "-n",
    type=int,
    default=20,
    help="Max entries to show (default 20).",
)
def outcome_list(filter_status: Optional[str], limit: int):
    """List recent outcomes."""
    store = OutcomeStore()
    outcomes = store.list_all()

    if filter_status:
        outcomes = [o for o in outcomes if o.status == filter_status]

    # Sort by recorded_at descending
    outcomes.sort(key=lambda o: o.recorded_at, reverse=True)
    outcomes = outcomes[:limit]

    if not outcomes:
        click.echo("No outcomes recorded.")
        return

    # Table header
    click.echo(
        f"  {'#':<4}{'ID':<10}{'Score':<8}{'Severity':<10}"
        f"{'Apply':<10}{'Link':<10}{'Status':<10}{'Recorded':<12}"
    )
    click.echo("  " + "-" * 72)

    for i, oc in enumerate(outcomes, 1):
        score_str = f"{oc.score:.0f}" if oc.status != "applied" or oc.score > 0 else "-"
        sev_str = oc.severity.upper() if oc.score > 0 else "-"
        apply_str = oc.apply_result
        if oc.link_type == "fingerprint":
            link_str = "linked"
        elif oc.status == "applied":
            link_str = "unlinked"
        else:
            link_str = "-"
        date_str = oc.recorded_at[:10] if oc.recorded_at else "-"

        click.echo(
            f"  {i:<4}{oc.outcome_id:<10}{score_str:<8}{sev_str:<10}"
            f"{apply_str:<10}{link_str:<10}{oc.status:<10}{date_str:<12}"
        )


@outcome.command("show")
@click.argument("outcome_id")
def outcome_show(outcome_id: str):
    """Show full details of an outcome."""
    store = OutcomeStore()
    oc = store.get(outcome_id)

    if oc is None:
        click.echo(f"Outcome not found: {outcome_id}")
        raise SystemExit(1)

    click.echo(f"Outcome: {oc.outcome_id}")
    click.echo(f"  Status:           {oc.status}")
    click.echo(f"  Plan fingerprint: {oc.plan_fingerprint or '-'}")
    click.echo(f"  Link type:        {oc.link_type}")
    click.echo(f"  Recorded at:      {oc.recorded_at}")
    click.echo("")

    if oc.score > 0 or oc.severity != "low":
        click.echo("Analysis Context:")
        click.echo(f"  Score:            {oc.score:.1f}")
        click.echo(f"  Severity:         {oc.severity.upper()}")
        click.echo(f"  Resource count:   {oc.resource_count}")
        if oc.resource_types:
            click.echo(f"  Resource types:   {', '.join(oc.resource_types)}")
        if oc.commit_sha:
            click.echo(f"  Commit:           {oc.commit_sha}")
        if oc.pr_number:
            click.echo(f"  PR:               #{oc.pr_number}")
        if oc.top_checks:
            click.echo("  Top checks:")
            for chk in oc.top_checks:
                source = chk.get("source", "")
                check_text = chk.get("check", "")
                click.echo(f"    - [{source}] {check_text}")
        click.echo("")

    click.echo("Apply Result:")
    click.echo(f"  Result:           {oc.apply_result}")
    if oc.applied_at:
        click.echo(f"  Applied at:       {oc.applied_at}")
    if oc.apply_commit_sha:
        click.echo(f"  Apply commit:     {oc.apply_commit_sha}")
    if oc.apply_error_codes:
        click.echo(f"  Error codes:      {', '.join(oc.apply_error_codes)}")
    if oc.apply_error_output:
        click.echo("  Error output:")
        for line in oc.apply_error_output.splitlines()[:10]:
            click.echo(f"    {line}")
