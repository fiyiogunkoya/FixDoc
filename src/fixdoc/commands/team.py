"""`fixdoc team` — SaaS-only commands for syncing with the team fix database.

Subcommands:
  status  — show login state, API URL, team, last push/pull times
  push    — upload local fixes to the team DB (dedup via content_hash)
  pull    — download team fixes into the local store
  search  — full-text search against the team DB
"""
from __future__ import annotations

from typing import List

import click

from ..cloud import (
    CloudClient,
    CloudError,
    fix_to_cloud_payload,
    load_credentials,
    touch_last_pull,
    touch_last_push,
)
from ..models import Fix
from ..storage import FixRepository


def _require_client(ctx) -> CloudClient:
    base_path = ctx.obj["base_path"]
    creds = load_credentials(base_path)
    try:
        return CloudClient(creds)
    except CloudError as exc:
        raise click.ClickException(
            f"{exc}\nRun `fixdoc login` to authenticate."
        )


@click.group("team")
def team():
    """Sync fixes with your team's cloud database."""


@team.command("status")
@click.pass_context
def status(ctx):
    """Show cloud login state and last sync timestamps."""
    base_path = ctx.obj["base_path"]
    creds = load_credentials(base_path)
    if not creds.is_logged_in():
        click.secho("Not logged in.", fg="yellow")
        click.echo("Run `fixdoc login` to connect to FixDoc Cloud.")
        return

    click.echo(f"API:        {creds.api_url}")
    click.echo(f"Team:       {creds.team_slug or '<unknown>'}")
    click.echo(f"Last push:  {creds.last_push_at or 'never'}")
    click.echo(f"Last pull:  {creds.last_pull_at or 'never'}")


@team.command("push")
@click.option(
    "--include-private",
    is_flag=True,
    help="Upload fixes flagged as private (default: skip them).",
)
@click.option("--dry-run", is_flag=True, help="Show what would be pushed without uploading.")
@click.pass_context
def push(ctx, include_private, dry_run):
    """Upload local fixes to the team database."""
    base_path = ctx.obj["base_path"]
    repo = FixRepository(base_path)

    fixes: List[Fix] = repo.list_all()
    if not include_private:
        fixes = [f for f in fixes if not f.is_private]

    if not fixes:
        click.echo("No fixes to push.")
        return

    if dry_run:
        click.echo(f"Would push {len(fixes)} fix(es):")
        for f in fixes[:10]:
            click.echo(f"  - {f.id[:8]} {f.issue[:72]}")
        if len(fixes) > 10:
            click.echo(f"  ... and {len(fixes) - 10} more")
        return

    client = _require_client(ctx)
    payloads = [fix_to_cloud_payload(f) for f in fixes]

    # Batch at 100 per request to keep payloads modest
    total_created = 0
    total_dup = 0
    for batch_start in range(0, len(payloads), 100):
        batch = payloads[batch_start : batch_start + 100]
        try:
            result = client.push_fixes(batch)
        except CloudError as exc:
            raise click.ClickException(f"Push failed: {exc}")
        total_created += result.get("created", 0)
        total_dup += result.get("duplicates", 0)

    touch_last_push(client.credentials, base_path=base_path)
    click.secho(
        f"Pushed {len(fixes)} fix(es): {total_created} new, {total_dup} duplicate.",
        fg="green",
    )


@team.command("pull")
@click.option("--limit", type=int, default=500, help="Max fixes to fetch in one pull.")
@click.pass_context
def pull(ctx, limit):
    """Download team fixes into the local store (dedups by content_hash)."""
    client = _require_client(ctx)
    base_path = ctx.obj["base_path"]
    repo = FixRepository(base_path)

    try:
        resp = client.pull_fixes(limit=limit)
    except CloudError as exc:
        raise click.ClickException(f"Pull failed: {exc}")

    items = resp.get("items", []) if isinstance(resp, dict) else []
    added = 0
    for item in items:
        fix = Fix(
            issue=item["issue"],
            resolution=item["resolution"],
            error_excerpt=item.get("error_excerpt"),
            tags=",".join(item["tags"]) if item.get("tags") else None,
            notes=item.get("notes"),
            author=item.get("author"),
            author_email=item.get("author_email"),
            is_private=item.get("is_private", False),
            source_error_ids=item.get("source_error_ids"),
            memory_type=item.get("memory_type", "fix"),
        )
        saved = repo.save(fix)
        # FixRepository.save returns the existing fix if content_hash matches,
        # so we detect "new" by comparing IDs
        if saved.id == fix.id:
            added += 1

    touch_last_pull(client.credentials, base_path=base_path)
    click.secho(f"Pulled {len(items)} fix(es); {added} new locally.", fg="green")


@team.command("search")
@click.argument("query")
@click.option("--limit", type=int, default=20)
@click.pass_context
def search_team(ctx, query, limit):
    """Search the team fix database."""
    client = _require_client(ctx)
    try:
        items = client.search_fixes(query, limit=limit)
    except CloudError as exc:
        raise click.ClickException(f"Search failed: {exc}")

    if not items:
        click.echo("No matches.")
        return

    click.echo(f"Found {len(items)} match(es):\n")
    for item in items:
        click.secho(item.get("issue", ""), bold=True)
        resolution = (item.get("resolution") or "").split("\n")[0]
        click.echo(f"  {resolution[:100]}")
        tags = item.get("tags")
        if tags:
            click.echo(f"  tags: {', '.join(tags)}")
        click.echo("")
