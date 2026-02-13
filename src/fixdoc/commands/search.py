"""Search command for fixdoc CLI."""

import click

from ..storage import FixRepository
from ..formatter import fix_to_markdown


@click.command()
@click.argument("query")
@click.option("--limit", "-l", type=int, default=None, help="Max results to show")
@click.pass_context
def search(ctx, query: str, limit: int):
    """
    Search your fixes by keyword.

    Searches across issue, resolution, error excerpt, tags, and notes.

    \b
    Examples:
        fixdoc search "storage account"
        fixdoc search rbac
    """
    config = ctx.obj["config"]
    limit = limit if limit is not None else config.display.search_result_limit

    repo = FixRepository(ctx.obj["base_path"])
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
@click.pass_context
def show(ctx, fix_id: str):
    """
    Show full details of a fix.

    Accepts full or partial fix ID.

    \b
    Example:
        fixdoc show a1b2c3d4
    """
    repo = FixRepository(ctx.obj["base_path"])
    fix = repo.get(fix_id)

    if not fix:
        click.echo(f"No fix found with ID: '{fix_id}'")
        raise SystemExit(1)

    click.echo(fix_to_markdown(fix))
