"""`fixdoc login` — paste an API key generated from the web UI to enable SaaS.

The flow:
  1. User visits https://app.fixdoc.dev/settings → "Generate API key"
  2. Web UI displays `fd_live_...` once
  3. User runs `fixdoc login` → enters token → CLI calls `/api/v1/auth/cli-whoami`
     to resolve team context, then persists to `~/.fixdoc/cloud.yaml`
"""
from __future__ import annotations

import webbrowser

import click

from ..cloud import (
    CloudCredentials,
    CloudError,
    DEFAULT_API_URL,
    clear_credentials,
    load_credentials,
    probe_token,
    save_credentials,
)


@click.command("login")
@click.option(
    "--api-url",
    default=None,
    help="Override API URL (defaults to https://api.fixdoc.dev).",
)
@click.option(
    "--token",
    default=None,
    help="Paste token directly (skips interactive prompt; useful for scripts).",
)
@click.option("--no-browser", is_flag=True, help="Don't open the browser automatically.")
@click.pass_context
def login(ctx, api_url, token, no_browser):
    """Log in to FixDoc Cloud with an API key."""
    base_path = ctx.obj["base_path"]
    existing = load_credentials(base_path)
    api_url = api_url or existing.api_url or DEFAULT_API_URL

    settings_url = api_url.replace("://api.", "://app.").rstrip("/") + "/settings"
    if not no_browser and not token:
        try:
            webbrowser.open(settings_url)
        except Exception:
            pass
        click.echo(f"Open {settings_url} and generate an API key under 'CLI access'.")

    if not token:
        token = click.prompt("Paste your token (fd_live_...)", hide_input=True, type=str).strip()

    try:
        info = probe_token(api_url, token)
    except CloudError as exc:
        raise click.ClickException(str(exc))

    creds = CloudCredentials(
        api_url=api_url,
        token=token,
        team_id=info["team_id"],
        team_slug=info["team_slug"],
    )
    save_credentials(creds, base_path=base_path)

    click.secho(f"Logged in to {api_url}", fg="green")
    click.echo(f"  Team: {info['team_name']} ({info['team_slug']})")
    click.echo(f"  Key:  {info['api_key_name']}")


@click.command("logout")
@click.pass_context
def logout(ctx):
    """Clear stored cloud credentials."""
    base_path = ctx.obj["base_path"]
    clear_credentials(base_path)
    click.secho("Logged out.", fg="green")
