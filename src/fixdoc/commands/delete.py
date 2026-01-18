"""Delete command for fixdoc CLI."""

import click

from ..storage import FixRepository


def get_repo() -> FixRepository:
    """Get the fix repository instance."""
    return FixRepository()


@click.command()
@click.argument("fix_id")
@click.confirmation_option(prompt="Are you sure you want to delete this fix?")
def delete(fix_id: str):
    """
    Delete a fix by ID.
    """
    repo = get_repo()

    fix = repo.get(fix_id)
    if not fix:
        click.echo(f"No fix found with ID starting with '{fix_id}'")
        raise SystemExit(1)

    if repo.delete(fix_id):
        click.echo(f"✓ Deleted fix: {fix.id[:8]}")
    else:
        click.echo("Failed to delete fix")
        raise SystemExit(1)
