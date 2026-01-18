"""Capture handlers for different input types."""

from typing import Optional

import click

from ..models import Fix
from ..terraform_parser import parse_terraform_output


def handle_terraform_capture(output: str, tags: Optional[str]) -> Optional[Fix]:
    ## Handle terraform output
    errors = parse_terraform_output(output)

    if not errors:
        click.echo("No terraform errors found", err=True)
        return None

    err = errors[0]

    click.echo("─" * 40)
    click.echo("Captured from terraform:\n")
    click.echo(f"  Resource: {err.resource_address}")
    if err.file:
        click.echo(f"  File:     {err.file}:{err.line}")
    click.echo(f"  Error:    {err.short_error()}")
    click.echo("─" * 40)

    resolution = click.prompt("\nWhat fixed it?")
    issue = f"{err.resource_address}: {err.short_error()}"

    # Auto-generate tags
    auto_tags = err.resource_type
    if tags:
        auto_tags = f"{err.resource_type},{tags}"
    if err.error_code:
        auto_tags = f"{auto_tags},{err.error_code}"

    final_tags = click.prompt("Tags", default=auto_tags, show_default=True)

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=output[:2000],
        tags=final_tags,
        notes=f"File: {err.file}:{err.line}" if err.file else None,
    )


def handle_generic_piped_capture(piped_input: str, tags: Optional[str]) -> Fix:
    """Handle generic piped input - treat as error excerpt."""
    click.echo("Captured input. Please provide fix details:\n")

    issue = click.prompt("What was the issue?")
    resolution = click.prompt("How was it resolved?")

    if not tags:
        tags = click.prompt("Tags (optional)", default="", show_default=False)

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=piped_input[:2000],
        tags=tags or None,
    )


def handle_quick_capture(quick: str, tags: Optional[str]) -> Fix:
    """Handle quick capture mode."""
    if "|" in quick:
        parts = quick.split("|", 1)
        issue = parts[0].strip()
        resolution = parts[1].strip()
    else:
        issue = quick.strip()
        resolution = click.prompt("Resolution")

    return Fix(issue=issue, resolution=resolution, tags=tags)


def handle_interactive_capture(tags: Optional[str]) -> Fix:
    """Handle interactive capture mode."""
    click.echo("Capturing a new fix...\n")

    issue = click.prompt("What was the issue?")
    resolution = click.prompt("How was it resolved?")

    error_excerpt = click.prompt(
        "Error excerpt (optional)", default="", show_default=False
    )

    if not tags:
        tags = click.prompt("Tags (optional)", default="", show_default=False)

    notes = click.prompt("Notes (optional)", default="", show_default=False)

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=error_excerpt or None,
        tags=tags or None,
        notes=notes or None,
    )
