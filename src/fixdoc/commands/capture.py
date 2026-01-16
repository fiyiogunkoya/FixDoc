"""Capture command for fixdoc CLI."""

from typing import Optional

import click

from ..models import Fix
from ..storage import FixRepository


def get_repo() -> FixRepository:
    """Get the fix repository instance."""
    return FixRepository()


@click.command()
@click.option(
    "--quick",
    "-q",
    type=str,
    default=None,
    help="Quick capture: 'issue or resolution'",
)
@click.option(
    "--tags",
    "-t",
    type=str,
    default=None,
    help="Tags (comma-separated, e.g., 'azurerm_storage_account,rbac')",
)
def capture(quick: Optional[str], tags: Optional[str]):
    """
    Capture a fix.
    fixdoc capture -q "User access denied | Added contributor role" -t storage,rbac
    """
    repo = get_repo()

    if quick:
        fix = _quick_capture(quick, tags)
    else:
        fix = _interactive_capture(tags)

    saved_fix = repo.save(fix)

    click.echo(f"\n Fix captured: {saved_fix.id[:8]}")
    click.echo(f"Documentation saved to: ~/.fixdoc/docs/{saved_fix.id}.md")


def _quick_capture(quick: str, tags: Optional[str]) -> Fix:
    """Handle quick capture mode."""
    if "|" in quick:
        parts = quick.split("|", 1)
        issue = parts[0].strip()
        resolution = parts[1].strip()
    else:
        issue = quick.strip()
        resolution = click.prompt("Resolution")

    return Fix(issue=issue, resolution=resolution, tags=tags)


def _interactive_capture(tags: Optional[str]) -> Fix:
    """Handle interactive capture mode."""
    click.echo("Capturing a new fix...\n")

    issue = click.prompt("What was the issue?")
    resolution = click.prompt("How was it resolved?")

    error_excerpt = click.prompt(
        "Error excerpt (optional, Enter to skip)", default="", show_default=False
    )

    if not tags:
        tags = click.prompt(
            "Tags (optional, comma-separated)", default="", show_default=False
        )

    notes = click.prompt(
        "Notes (optional, gotchas or misleading directions)",
        default="",
        show_default=False,
    )

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=error_excerpt or None,
        tags=tags or None,
        notes=notes or None,
    )
