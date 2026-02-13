"""Capture handlers for different input types."""

from typing import Optional

import click

from ..config import FixDocConfig
from ..models import Fix
from ..parsers import (
    ErrorSource,
    KubernetesError,
    detect_and_parse,
    detect_error_source,
)
from ..storage import FixRepository
from ..suggestions import prompt_similar_fixes


def _excerpt_limit(config: Optional[FixDocConfig] = None) -> int:
    """Return the error excerpt max chars from config or default."""
    if config:
        return config.capture.error_excerpt_max_chars
    return 2000


def _suggestions_limit(config: Optional[FixDocConfig] = None) -> int:
    """Return the max suggestions shown from config or default."""
    if config:
        return config.capture.max_suggestions_shown
    return 3


def _similar_fix_limit(config: Optional[FixDocConfig] = None) -> int:
    """Return the similar fix limit from config or default."""
    if config:
        return config.capture.similar_fix_limit
    return 5


def handle_piped_input(
    output: str, tags: Optional[str], repo: Optional[FixRepository] = None,
    config: Optional[FixDocConfig] = None,
) -> Optional[Fix]:
    """
    Handle piped input by detecting the source and routing appropriately.

    This is the main entry point for piped input handling. It detects
    whether the input is from Terraform, Kubernetes, or another source.
    """
    source = detect_error_source(output)

    if source == ErrorSource.TERRAFORM:
        return handle_terraform_capture(output, tags, repo, config=config)
    elif source in (ErrorSource.KUBERNETES, ErrorSource.HELM):
        return handle_kubernetes_capture(output, tags, repo, config=config)
    else:
        return handle_generic_piped_capture(output, tags, repo, config=config)


def handle_terraform_capture(
    output: str, tags: Optional[str], repo: Optional[FixRepository] = None,
    config: Optional[FixDocConfig] = None,
) -> Optional[Fix]:
    """Handle Terraform output with multi-cloud support."""
    errors = detect_and_parse(output)

    if not errors:
        click.echo("No Terraform errors found in input", err=True)
        return None

    # Use the first error (or could prompt to select)
    err = errors[0]

    max_suggestions = _suggestions_limit(config)

    # Display captured error info
    click.echo("─" * 50)
    click.echo("Captured from Terraform:\n")
    click.echo(f"  Provider: {err.cloud_provider.value.upper()}")
    click.echo(f"  Resource: {err.resource_address}")
    if err.file:
        click.echo(f"  File:     {err.file}:{err.line}")
    if err.error_code:
        click.echo(f"  Code:     {err.error_code}")
    click.echo(f"  Error:    {err.short_error()}")

    # Show suggestions if available
    if err.suggestions:
        click.echo("\n  Suggestions:")
        for suggestion in err.suggestions[:max_suggestions]:
            click.echo(f"    • {suggestion}")

    click.echo("─" * 50)

    # If multiple errors, show count
    if len(errors) > 1:
        click.echo(f"\n  ({len(errors) - 1} additional error(s) not shown)\n")

    # Check for similar existing fixes before prompting for resolution
    if repo:
        auto_tags = err.generate_tags()
        if tags:
            auto_tags = f"{auto_tags},{tags}"
        existing_fix = prompt_similar_fixes(
            repo, output, auto_tags, limit=_similar_fix_limit(config),
        )
        if existing_fix:
            click.echo(f"\n Using existing fix: {existing_fix.id[:8]}")
            click.echo(f"  Resolution: {existing_fix.resolution[:80]}...")
            return None  # Don't create a new fix

    # Prompt for resolution
    resolution = click.prompt("\n What fixed this?")
    issue = err.to_issue_string()

    # Auto-generate tags (recalculate since we may not have hit similar fixes)
    auto_tags = err.generate_tags()
    if tags:
        auto_tags = f"{auto_tags},{tags}"

    final_tags = click.prompt("Tags", default=auto_tags, show_default=True)

    # Optional notes
    notes_default = ""
    if err.file:
        notes_default = f"File: {err.file}:{err.line}"
    if err.suggestions:
        notes_default += "\nSuggestions: " + "; ".join(err.suggestions[:2])

    notes = click.prompt("Notes (optional)", default=notes_default, show_default=False)

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=output[:_excerpt_limit(config)],
        tags=final_tags,
        notes=notes or None,
    )


def handle_kubernetes_capture(
    output: str, tags: Optional[str], repo: Optional[FixRepository] = None,
    config: Optional[FixDocConfig] = None,
) -> Optional[Fix]:
    """Handle Kubernetes (kubectl/Helm) output."""
    errors = detect_and_parse(output)

    if not errors:
        click.echo("No Kubernetes errors found in input", err=True)
        return None

    err = errors[0]

    max_suggestions = _suggestions_limit(config)

    # Display captured error info
    click.echo("─" * 50)

    # Determine source label
    if hasattr(err, 'helm_release') and err.helm_release:
        source_label = "Helm"
    else:
        source_label = "Kubernetes"

    click.echo(f"Captured from {source_label}:\n")

    if err.namespace:
        click.echo(f"  Namespace: {err.namespace}")
    if err.resource_type:
        click.echo(f"  Resource:  {err.resource_type}/{err.resource_name or 'unknown'}")

    # Kubernetes-specific fields
    if isinstance(err, KubernetesError):
        if err.helm_release:
            click.echo(f"  Release:   {err.helm_release}")
        if err.helm_chart:
            click.echo(f"  Chart:     {err.helm_chart}")
        if err.pod_name:
            click.echo(f"  Pod:       {err.pod_name}")
        if err.restart_count is not None:
            click.echo(f"  Restarts:  {err.restart_count}")
        if err.exit_code is not None:
            click.echo(f"  Exit Code: {err.exit_code}")

    if err.error_code:
        click.echo(f"  Status:    {err.error_code}")
    click.echo(f"  Error:     {err.short_error()}")

    # Show suggestions if available
    if err.suggestions:
        click.echo("\n  Suggestions:")
        for suggestion in err.suggestions[:max_suggestions]:
            click.echo(f"    • {suggestion}")

    click.echo("─" * 50)

    # If multiple errors, show count
    if len(errors) > 1:
        click.echo(f"\n  ({len(errors) - 1} additional error(s) not shown)\n")

    # Check for similar existing fixes before prompting for resolution
    if repo:
        auto_tags = err.generate_tags()
        if tags:
            auto_tags = f"{auto_tags},{tags}"
        existing_fix = prompt_similar_fixes(
            repo, output, auto_tags, limit=_similar_fix_limit(config),
        )
        if existing_fix:
            click.echo(f"\n Using existing fix: {existing_fix.id[:8]}")
            click.echo(f"  Resolution: {existing_fix.resolution[:80]}...")
            return None  # Don't create a new fix

    # Prompt for resolution
    resolution = click.prompt("\n What fixed this?")
    issue = err.to_issue_string()

    # Auto-generate tags (recalculate since we may not have hit similar fixes)
    auto_tags = err.generate_tags()
    if tags:
        auto_tags = f"{auto_tags},{tags}"

    final_tags = click.prompt("Tags", default=auto_tags, show_default=True)

    # Optional notes with helpful context
    notes_parts = []
    if isinstance(err, KubernetesError):
        if err.namespace:
            notes_parts.append(f"Namespace: {err.namespace}")
        if err.pod_name:
            notes_parts.append(f"Pod: {err.pod_name}")
    if err.suggestions:
        notes_parts.append("Suggestions: " + "; ".join(err.suggestions[:2]))

    notes_default = "\n".join(notes_parts)
    notes = click.prompt("Notes (optional)", default=notes_default, show_default=False)

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=output[:_excerpt_limit(config)],
        tags=final_tags,
        notes=notes or None,
    )


def handle_generic_piped_capture(
    piped_input: str, tags: Optional[str], repo: Optional[FixRepository] = None,
    config: Optional[FixDocConfig] = None,
) -> Optional[Fix]:
    """Handle generic piped input - treat as error excerpt."""
    click.echo("─" * 50)
    click.echo("Captured generic input (unknown source)")
    click.echo("─" * 50)

    # Check for similar existing fixes before prompting for details
    if repo:
        existing_fix = prompt_similar_fixes(
            repo, piped_input, tags, limit=_similar_fix_limit(config),
        )
        if existing_fix:
            click.echo(f"\n Using existing fix: {existing_fix.id[:8]}")
            click.echo(f"  Resolution: {existing_fix.resolution[:80]}...")
            return None  # Don't create a new fix

    click.echo("\nPlease provide fix details:\n")

    issue = click.prompt("What was the issue?")
    resolution = click.prompt("How was it resolved?")

    if not tags:
        tags = click.prompt("Tags (optional)", default="", show_default=False)

    notes = click.prompt("Notes (optional)", default="", show_default=False)

    return Fix(
        issue=issue,
        resolution=resolution,
        error_excerpt=piped_input[:_excerpt_limit(config)],
        tags=tags or None,
        notes=notes or None,
    )


def handle_quick_capture(
    quick: str, tags: Optional[str], repo: Optional[FixRepository] = None
) -> Optional[Fix]:
    """Handle quick capture mode."""
    # Check for similar existing fixes before creating new one
    if repo:
        existing_fix = prompt_similar_fixes(repo, quick, tags)
        if existing_fix:
            click.echo(f"\n Using existing fix: {existing_fix.id[:8]}")
            click.echo(f"  Resolution: {existing_fix.resolution[:80]}...")
            return None  # Don't create a new fix

    if "|" in quick:
        parts = quick.split("|", 1)
        issue = parts[0].strip()
        resolution = parts[1].strip()
    else:
        issue = quick.strip()
        resolution = click.prompt("Resolution")

    return Fix(issue=issue, resolution=resolution, tags=tags)


def handle_interactive_capture(
    tags: Optional[str], repo: Optional[FixRepository] = None
) -> Optional[Fix]:
    """Handle interactive capture mode."""
    click.echo("─" * 50)
    click.echo("Capturing a new fix...")
    click.echo("─" * 50)
    click.echo()

    issue = click.prompt("What was the issue?")

    # Check for similar existing fixes after user enters issue
    if repo:
        existing_fix = prompt_similar_fixes(repo, issue, tags)
        if existing_fix:
            click.echo(f"\n Using existing fix: {existing_fix.id[:8]}")
            click.echo(f"  Resolution: {existing_fix.resolution[:80]}...")
            return None  # Don't create a new fix

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


def handle_multi_error_capture(output: str, tags: Optional[str]) -> list[Fix]:
    """
    Handle output with multiple errors, creating a fix for each.

    This is useful for batch processing multiple errors from a single
    Terraform apply or kubectl operation.
    """
    errors = detect_and_parse(output)

    if not errors:
        click.echo("No errors found in input", err=True)
        return []

    fixes = []

    click.echo(f"\nFound {len(errors)} error(s). Processing each:\n")

    for i, err in enumerate(errors, 1):
        click.echo("─" * 50)
        click.echo(f"Error {i}/{len(errors)}:")
        click.echo(f"  Resource: {err.resource_address or err.resource_name or 'unknown'}")
        click.echo(f"  Error:    {err.short_error()}")
        click.echo("─" * 50)

        # Ask if user wants to create a fix for this error
        create = click.confirm(f"Create fix for this error?", default=True)
        if not create:
            continue

        resolution = click.prompt("What fixed this?")
        issue = err.to_issue_string()

        auto_tags = err.generate_tags()
        if tags:
            auto_tags = f"{auto_tags},{tags}"

        final_tags = click.prompt("Tags", default=auto_tags, show_default=True)

        fix = Fix(
            issue=issue,
            resolution=resolution,
            error_excerpt=err.raw_output[:2000],
            tags=final_tags,
        )
        fixes.append(fix)

        click.echo(f"✓ Fix created\n")

    return fixes
