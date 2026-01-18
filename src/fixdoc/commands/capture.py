"""Capture command for fixdoc CLI."""

import sys
from typing import Optional

import click

from ..models import Fix
from ..storage import FixRepository
from ..terraform_parser import is_terraform_output
from .capture_handlers import (
    handle_terraform_capture,
    handle_generic_piped_capture,
    handle_quick_capture,
    handle_interactive_capture,
)


def get_repo() -> FixRepository:
    return FixRepository()


@click.command()
@click.option(
    "--quick", "-q", type=str, default=None,
    help="Quick capture: 'issue | resolution'",
)
@click.option(
    "--tags", "-t", type=str, default=None,
    help="Tags (comma-separated)",
)
def capture(quick: Optional[str], tags: Optional[str]):
    """
    Capture a new fix.

    \b
    Pipe terraform errors:
        terraform apply 2>&1 | fixdoc capture

    \b
    Interactive:
        fixdoc capture

    \b
    Quick:
        fixdoc capture -q "issue | resolution" -t storage,rbac
    """
    repo = get_repo()

    # Check for piped input
    if not sys.stdin.isatty():
        fix = _handle_piped_input(tags)
    elif quick:
        fix = handle_quick_capture(quick, tags)
    else:
        fix = handle_interactive_capture(tags)

    if fix:
        saved = repo.save(fix)
        click.echo(f"\n Fix captured: {saved.id[:8]}")
        click.echo(f" Markdown: ~/.fixdoc/docs/{saved.id}.md")


def _handle_piped_input(tags: Optional[str]) -> Optional[Fix]:
    ## Route piped input to handler 
    piped_input = sys.stdin.read()

    if not piped_input.strip():
        click.echo("No input received.", err=True)
        return None

    if is_terraform_output(piped_input):
        return handle_terraform_capture(piped_input, tags)

    return handle_generic_piped_capture(piped_input, tags)
