"""Deduplicate command for fixdoc CLI."""

from collections import defaultdict

import click

from ..models import compute_content_hash
from ..storage import FixRepository


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show duplicates without deleting.",
)
@click.option(
    "--keep",
    type=click.Choice(["oldest", "newest"]),
    default="oldest",
    help="Which duplicate to keep (default: oldest).",
)
@click.pass_context
def deduplicate(ctx, dry_run, keep):
    """Remove duplicate fixes from the database.

    Groups fixes by content hash and keeps one per group.
    Prefers keeping fixes that have tracking data (applied_count, source_error_ids).
    """
    repo = FixRepository(ctx.obj["base_path"])
    fixes = repo.list_all()

    # Group by content_hash
    groups = defaultdict(list)
    for fix in fixes:
        groups[fix.content_hash].append(fix)

    total_removed = 0
    for content_hash, group in groups.items():
        if len(group) < 2:
            continue

        # Sort by created_at for oldest/newest selection
        group.sort(key=lambda f: f.created_at)

        # Pick the keeper: prefer fixes with tracking data
        keeper = _pick_keeper(group, keep)
        duplicates = [f for f in group if f.id != keeper.id]

        if dry_run:
            click.echo(
                f"  [{keeper.issue[:50]}] — keeping {keeper.id[:8]}, "
                f"would remove {len(duplicates)} duplicate(s)"
            )
        else:
            for dup in duplicates:
                repo.delete(dup.id)
            click.echo(
                f"  [{keeper.issue[:50]}] — kept {keeper.id[:8]}, "
                f"removed {len(duplicates)}"
            )

        total_removed += len(duplicates)

    if total_removed == 0:
        click.echo("No duplicates found.")
    elif dry_run:
        click.echo(f"\n{total_removed} duplicate(s) would be removed.")
    else:
        click.echo(f"\n{total_removed} duplicate(s) removed.")


def _pick_keeper(group, keep):
    """Pick the best fix to keep from a group of duplicates.

    Prefers fixes with applied_count > 0 or source_error_ids.
    Falls back to oldest/newest by created_at.
    """
    # Fixes with tracking data are preferred
    tracked = [
        f for f in group
        if f.applied_count > 0 or f.source_error_ids
    ]
    candidates = tracked if tracked else group

    if keep == "newest":
        return max(candidates, key=lambda f: f.created_at)
    return min(candidates, key=lambda f: f.created_at)
