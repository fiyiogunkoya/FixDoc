"""Delete command for fixdoc CLI."""

import click

from ..storage import FixRepository


def get_repo() -> FixRepository:
    """Get the fix repository instance."""
    return FixRepository()


@click.command()
@click.argument("fix_id", required=False)
@click.option("--purge", is_flag=True, help="Delete all fixes")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete(fix_id: str, purge: bool, yes: bool):
    """
    Delete a fix by ID, or purge all fixes.

    \b
    Examples:
        fixdoc delete a1b2c3d4
        fixdoc delete --purge
        fixdoc delete --purge -y
    """
    repo = get_repo()

    if purge:
        _purge_all(repo, yes)
    elif fix_id:
        _delete_one(repo, fix_id, yes)
    else:
        click.echo("Provide a fix ID or use --purge to delete all.")
        raise SystemExit(1)


def _purge_all(repo: FixRepository, skip_confirm: bool):
    """Delete all fixes."""
    count = repo.count()

    if count == 0:
        click.echo("No fixes to delete.")
        return

    if not skip_confirm:
        if not click.confirm(f"Delete all {count} fixes?"):
            click.echo("Aborted.")
            return

    repo.purge()
    click.echo(f"✓ Purged {count} fixes.")


def _delete_one(repo: FixRepository, fix_id: str, skip_confirm: bool):
    """Delete a single fix."""
    fix = repo.get(fix_id)

    if not fix:
        click.echo(f"No fix found with ID starting with '{fix_id}'")
        raise SystemExit(1)

    if not skip_confirm:
        if not click.confirm(f"Delete fix {fix.id[:8]}?"):
            click.echo("Aborted.")
            return

    if repo.delete(fix_id):
        click.echo(f"✓ Deleted fix: {fix.id[:8]}")
    else:
        click.echo("Failed to delete fix")
        raise SystemExit(1)