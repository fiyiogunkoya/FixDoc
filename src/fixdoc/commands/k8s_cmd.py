"""Kubernetes change intelligence CLI commands for fixdoc."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

from ..k8s.catalog import (
    build_merged_catalog,
    list_categories,
    list_changes,
    load_custom_entries,
    resolve_change,
)
from ..k8s.engine import analyze_k8s_change
from ..k8s.formatting import format_human, format_json, format_markdown
from ..k8s.snapshot import capture_cluster_snapshot, load_snapshot, save_snapshot
from ..storage import FixRepository


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _get_merged_catalog():
    """Load custom entries and merge with built-in catalog."""
    custom = load_custom_entries()
    return build_merged_catalog(custom)


@click.group("k8s")
def k8s_group():
    """Kubernetes change intelligence — analyze platform change impact."""
    pass


@k8s_group.command("analyze")
@click.option(
    "--change", "change_category", required=True,
    help="Change category to analyze (e.g. os-upgrade, k8s-version, ingress-controller, node-pool-sku, or custom).",
)
@click.option("--from", "from_version", required=True, help="Source version (e.g. azurelinux:2.0, 1.28).")
@click.option("--to", "to_version", required=True, help="Target version (e.g. azurelinux:3.0, 1.29).")
@click.option("--cluster", is_flag=True, default=False, help="Introspect live cluster via kubectl.")
@click.option("--snapshot", "snapshot_path", default=None, help="Path to cluster snapshot JSON file.")
@click.option("--format", "-f", "output_format", type=click.Choice(["human", "json", "markdown"]), default="human",
              help="Output format.")
@click.option(
    "--exit-on", "exit_on",
    type=click.Choice(["low", "medium", "high", "critical"]),
    default=None,
    help="Exit with code 1 if severity meets or exceeds this threshold. For CI gating.",
)
@click.option("--namespace", "-n", "namespace", default=None,
              help="Limit cluster introspection to this namespace.")
@click.option("--kubeconfig", default=None, help="Explicit kubeconfig path.")
@click.option("--verbose", "-v", is_flag=True, help="Show full workload list.")
@click.pass_context
def k8s_analyze(
    ctx,
    change_category: str,
    from_version: str,
    to_version: str,
    cluster: bool,
    snapshot_path: Optional[str],
    output_format: str,
    exit_on: Optional[str],
    namespace: Optional[str],
    kubeconfig: Optional[str],
    verbose: bool,
):
    """Analyze the impact of a Kubernetes platform change.

    Examples:

    \b
        fixdoc k8s analyze --change os-upgrade --from azurelinux:2.0 --to azurelinux:3.0
        fixdoc k8s analyze --change os-upgrade --from azurelinux:2.0 --to azurelinux:3.0 --cluster
        fixdoc k8s analyze --change k8s-version --from 1.28 --to 1.29 --snapshot cluster.json
        fixdoc k8s analyze --change node-pool-sku --from Standard_D2s_v3 --to Standard_D4s_v3

    \b
    Options:
        --change        Change category (required)
        --from/--to     Version transition (required)
        --cluster       Introspect live cluster via kubectl
        --snapshot      Load cluster snapshot from JSON file
        --format/-f     Output format: human, json, or markdown
        --exit-on       Exit code 1 if severity >= threshold (for CI gating)
    """
    # Load cluster snapshot if requested
    snapshot = None
    if snapshot_path:
        try:
            snapshot = load_snapshot(snapshot_path)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            click.echo(f"Error loading snapshot: {exc}", err=True)
            sys.exit(1)
    elif cluster:
        click.echo("Capturing cluster snapshot...", err=True)
        snapshot = capture_cluster_snapshot(kubeconfig=kubeconfig, namespace=namespace)
        click.echo(
            f"  Found {len(snapshot.workloads)} workloads, "
            f"{len(snapshot.node_pools)} node pools, "
            f"{len(snapshot.ingresses)} ingresses",
            err=True,
        )

    # Load fix repository for team knowledge
    repo = None
    try:
        base_path = ctx.obj.get("base_path") if ctx.obj else None
        if base_path:
            repo = FixRepository(Path(base_path) if isinstance(base_path, str) else base_path)
    except Exception:
        pass

    # Load merged catalog (built-in + custom)
    merged = _get_merged_catalog()

    # Run analysis
    result = analyze_k8s_change(
        category=change_category,
        from_version=from_version,
        to_version=to_version,
        snapshot=snapshot,
        repo=repo,
        catalog=merged,
    )

    # Output
    if output_format == "json":
        click.echo(format_json(result))
    elif output_format == "markdown":
        click.echo(format_markdown(result))
    else:
        click.echo(format_human(result, verbose=verbose))

    # CI gating
    if exit_on is not None:
        threshold_rank = _SEVERITY_ORDER.get(exit_on, 0)
        actual_rank = _SEVERITY_ORDER.get(result.severity, 0)
        if actual_rank >= threshold_rank:
            sys.exit(1)


@k8s_group.command("snapshot")
@click.option("-o", "--output", "output_path", required=True, help="Output path for snapshot JSON.")
@click.option("--namespace", "-n", "namespace", default=None,
              help="Limit introspection to this namespace.")
@click.option("--kubeconfig", default=None, help="Explicit kubeconfig path.")
def k8s_snapshot(output_path: str, namespace: Optional[str], kubeconfig: Optional[str]):
    """Capture a cluster snapshot to a JSON file.

    Examples:

    \b
        fixdoc k8s snapshot -o my-cluster.json
        fixdoc k8s snapshot --namespace prod -o prod-snapshot.json
    """
    click.echo("Capturing cluster snapshot...", err=True)
    snapshot = capture_cluster_snapshot(kubeconfig=kubeconfig, namespace=namespace)
    save_snapshot(snapshot, output_path)
    click.echo(
        f"Snapshot saved to {output_path} "
        f"({len(snapshot.workloads)} workloads, "
        f"{len(snapshot.node_pools)} node pools, "
        f"{len(snapshot.ingresses)} ingresses)",
        err=True,
    )


@k8s_group.command("changes")
@click.option("--category", default=None, help="Filter by category.")
def k8s_changes(category: Optional[str]):
    """List available change catalog entries.

    Examples:

    \b
        fixdoc k8s changes
        fixdoc k8s changes --category os-upgrade
    """
    merged = _get_merged_catalog()
    entries = list_changes(category, catalog=merged)

    if not entries:
        click.echo("No catalog entries found.")
        return

    click.echo("")
    click.echo("  Available Change Catalog Entries")
    click.echo("  " + "=" * 50)
    click.echo("")

    for entry in entries:
        bc_count = len(entry.breaking_changes)
        severities = [bc.severity for bc in entry.breaking_changes]
        max_sev = "none"
        for s in ["critical", "high", "medium", "low"]:
            if s in severities:
                max_sev = s
                break

        source_label = "custom" if entry.source != "built-in" else "built-in"
        click.echo(f"  [{entry.category}] {entry.display_name} [{source_label}]")
        click.echo(f"    {entry.from_version} -> {entry.to_version}")
        click.echo(f"    {bc_count} breaking changes (max severity: {max_sev})")
        click.echo("")

    click.echo(f"  Categories: {', '.join(list_categories(catalog=merged))}")
    click.echo("")


# ---------------------------------------------------------------------------
# catalog subgroup
# ---------------------------------------------------------------------------


@k8s_group.group("catalog")
def k8s_catalog():
    """Manage the K8s change catalog."""
    pass


@k8s_catalog.command("generate")
@click.option("--change", "change_category", required=True,
              help="Change category (e.g. os-upgrade, k8s-version, ingress-controller, node-pool-sku, or custom).")
@click.option("--from", "from_version", required=True, help="Source version.")
@click.option("--to", "to_version", required=True, help="Target version.")
@click.option("--from-text", "from_text", default=None, help="Release notes as text.")
@click.option("--from-url", "from_url", default=None, help="URL to fetch release notes from.")
def k8s_catalog_generate(
    change_category: str,
    from_version: str,
    to_version: str,
    from_text: Optional[str],
    from_url: Optional[str],
):
    """Generate a catalog entry from release notes using AI.

    Provide release notes via --from-text, --from-url, or paste interactively.

    Examples:

    \b
        fixdoc k8s catalog generate --change k8s-version --from 1.29 --to 1.30 \\
            --from-text "PSP is removed in v1.30."
        fixdoc k8s catalog generate --change os-upgrade --from azurelinux:2.0 --to azurelinux:3.0
    """
    # Resolve release notes text
    release_notes = None
    if from_text:
        release_notes = from_text
    elif from_url:
        release_notes = _fetch_url_text(from_url)
        if release_notes is None:
            click.echo(f"Error: could not fetch {from_url}", err=True)
            sys.exit(1)
        click.echo(f"Fetched {len(release_notes)} chars from URL.", err=True)
    else:
        click.echo("Paste release notes (press Ctrl-D when done):", err=True)
        try:
            release_notes = sys.stdin.read()
        except KeyboardInterrupt:
            click.echo("\nAborted.", err=True)
            sys.exit(1)

    if not release_notes or not release_notes.strip():
        click.echo("Error: no release notes provided.", err=True)
        sys.exit(1)

    click.echo("Generating catalog entry with AI...", err=True)

    from ..k8s.generate import generate_catalog_entry, validate_generated_yaml

    yaml_text = generate_catalog_entry(
        category=change_category,
        from_version=from_version,
        to_version=to_version,
        release_notes=release_notes,
    )

    if yaml_text is None:
        click.echo(
            "Error: could not generate entry. "
            "Ensure anthropic is installed (pip install fixdoc[ai]) "
            "and ANTHROPIC_API_KEY is set.",
            err=True,
        )
        sys.exit(1)

    # Validate
    entry = validate_generated_yaml(yaml_text)
    if entry is None:
        click.echo("Warning: generated YAML did not validate. Raw output:", err=True)
        click.echo(yaml_text)
        sys.exit(1)

    # Write to .fixdoc-catalog/
    from ..pending import _find_git_root
    git_root = _find_git_root()
    catalog_dir = git_root / ".fixdoc-catalog"
    catalog_dir.mkdir(exist_ok=True)

    safe_from = from_version.replace(":", "-").replace("/", "-")
    safe_to = to_version.replace(":", "-").replace("/", "-")
    filename = f"{change_category}-{safe_from}-{safe_to}.yaml"
    out_path = catalog_dir / filename

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)
        if not yaml_text.endswith("\n"):
            f.write("\n")

    # Summary
    bc_count = len(entry.breaking_changes)
    severities = {}
    for bc in entry.breaking_changes:
        severities[bc.severity] = severities.get(bc.severity, 0) + 1
    sev_str = ", ".join(f"{k}: {v}" for k, v in severities.items()) if severities else "none"

    click.echo(f"\nGenerated {bc_count} breaking changes ({sev_str})", err=True)
    click.echo(f"Written to {out_path}", err=True)
    click.echo("Review the file and commit when ready.", err=True)


def _fetch_url_text(url: str) -> Optional[str]:
    """Fetch text content from a URL."""
    try:
        from urllib.request import urlopen, Request
        req = Request(url, headers={"User-Agent": "fixdoc/0.1"})
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
