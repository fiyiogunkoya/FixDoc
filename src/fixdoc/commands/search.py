"""Search command for fixdoc CLI."""

import click

from ..storage import FixRepository
from ..formatter import fix_to_markdown


def get_repo() -> FixRepository:
    """Get the fix repository instance."""
    return FixRepository()


@click.command()
@click.argument("query")
@click.option("--limit", "-l", type=int, default=10, help="Max results to show")
def search(query: str, limit: int):
    """
    Search your fixes by keyword.

    Searches across issue, resolution, error excerpt, tags, and notes.

    \b
    Examples:
        fixdoc search "storage account"
        fixdoc search rbac
    """
    repo = get_repo()
    results = repo.search(query)

    if not results:
        click.echo(f"No fixes found matching '{query}'")
        return

    click.echo(f"Found {len(results)} fix(es) matching '{query}':\n")

    for fix in results[:limit]:
        click.echo(f"  {fix.summary()}")

    if len(results) > limit:
        click.echo(f"\n  ... and {len(results) - limit} more. Use --limit to see more.")

    click.echo(f"\nRun `fixdoc show <fix-id>` for full details.")


@click.command()
@click.argument("fix_id")
def show(fix_id: str):
    """
    Show full details of a fix.

    Accepts full or partial fix ID.

    \b
    Example:
        fixdoc show a1b2c3d4
    """
    repo = get_repo()
    fix = repo.get(fix_id)

    if not fix:
        click.echo(f"No fix found with ID starting with '{fix_id}'")
        raise SystemExit(1)

    click.echo(fix_to_markdown(fix))
