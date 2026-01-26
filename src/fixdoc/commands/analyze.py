"""Analyze command for fixdoc CLI."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click

from ..models import Fix
from ..storage import FixRepository
from ..parsers.base import CloudProvider


@dataclass
class AnalysisMatch:
    """Represents a potential issue found during terraform plan analysis."""

    resource_address: str
    resource_type: str
    related_fix: Fix
    cloud_provider: CloudProvider = CloudProvider.UNKNOWN

    def format_warning(self) -> str:
        """Format as a warning message for CLI output."""
        short_id = self.related_fix.id[:8]
        issue = self.related_fix.issue
        resolution = self.related_fix.resolution

        issue_preview = issue[:80] + "..." if len(issue) > 80 else issue
        resolution_preview = resolution[:80] + "..." if len(resolution) > 80 else resolution

        lines = [
            f"⚠  {self.resource_address} may relate to FIX-{short_id}",
            f"   Previous issue: {issue_preview}",
            f"   Resolution: {resolution_preview}",
        ]

        if self.related_fix.tags:
            lines.append(f"   Tags: {self.related_fix.tags}")

        return "\n".join(lines)


@dataclass
class PlanResource:
    """Represents a resource in a Terraform plan."""

    address: str
    resource_type: str
    name: str
    cloud_provider: CloudProvider
    action: str  # create, update, delete, no-op
    module_path: Optional[str] = None
    values: dict = field(default_factory=dict)


class TerraformAnalyzer:
    """Analyzes terraform plan JSON output against known fixes."""

    def __init__(self, repo: Optional[FixRepository] = None):
        self.repo = repo or FixRepository()

    def load_plan(self, plan_path: Path) -> dict:
        """Load and parse a terraform plan JSON file."""
        with open(plan_path, "r") as f:
            return json.load(f)

    def detect_cloud_provider(self, resource_type: str, provider_name: str = "") -> CloudProvider:
        """Detect cloud provider from resource type or provider name."""
        resource_lower = resource_type.lower()
        provider_lower = provider_name.lower()

        if resource_lower.startswith("aws_") or "hashicorp/aws" in provider_lower:
            return CloudProvider.AWS
        elif resource_lower.startswith("azurerm_") or "hashicorp/azurerm" in provider_lower:
            return CloudProvider.AZURE
        elif resource_lower.startswith("google_") or "hashicorp/google" in provider_lower:
            return CloudProvider.GCP

        return CloudProvider.UNKNOWN

    def extract_resources(self, plan: dict) -> list[PlanResource]:
        """Extract all resources from a Terraform plan with full metadata."""
        resources = []

        # Extract from resource_changes (most reliable for planned changes)
        for change in plan.get("resource_changes", []):
            address = change.get("address", "")
            resource_type = change.get("type", "")
            name = change.get("name", "")
            provider_name = change.get("provider_name", "")

            if not resource_type:
                continue

            # Determine action
            actions = change.get("change", {}).get("actions", [])
            if "create" in actions:
                action = "create"
            elif "delete" in actions:
                action = "delete"
            elif "update" in actions:
                action = "update"
            else:
                action = "no-op"

            # Extract module path if present
            module_path = None
            if address.startswith("module."):
                parts = address.split(".")
                module_parts = []
                for i, part in enumerate(parts):
                    if part == "module" and i + 1 < len(parts):
                        module_parts.append(f"module.{parts[i + 1]}")
                module_path = ".".join(module_parts) if module_parts else None

            # Get planned values
            values = change.get("change", {}).get("after", {}) or {}

            resources.append(PlanResource(
                address=address,
                resource_type=resource_type,
                name=name,
                cloud_provider=self.detect_cloud_provider(resource_type, provider_name),
                action=action,
                module_path=module_path,
                values=values,
            ))

        # Also check planned_values for additional resources
        self._extract_from_planned_values(plan.get("planned_values", {}), resources)

        # Deduplicate by address
        seen = set()
        unique = []
        for r in resources:
            if r.address not in seen:
                seen.add(r.address)
                unique.append(r)

        return unique

    def _extract_from_planned_values(self, planned_values: dict, resources: list[PlanResource]):
        """Extract resources from planned_values section."""
        existing_addresses = {r.address for r in resources}

        def process_module(module: dict, prefix: str = ""):
            # Process resources in this module
            for resource in module.get("resources", []):
                address = resource.get("address", "")
                if address in existing_addresses:
                    continue

                resource_type = resource.get("type", "")
                if not resource_type:
                    continue

                provider_name = resource.get("provider_name", "")

                resources.append(PlanResource(
                    address=address,
                    resource_type=resource_type,
                    name=resource.get("name", ""),
                    cloud_provider=self.detect_cloud_provider(resource_type, provider_name),
                    action="unknown",
                    module_path=prefix or None,
                    values=resource.get("values", {}),
                ))
                existing_addresses.add(address)

            # Process child modules
            for child in module.get("child_modules", []):
                child_address = child.get("address", "")
                process_module(child, child_address)

        root = planned_values.get("root_module", {})
        process_module(root)

    def extract_resource_types(self, plan: dict) -> list[tuple[str, str]]:
        """Extract (resource_address, resource_type) tuples from a plan.

        This is a simplified version for backward compatibility.
        """
        resources = self.extract_resources(plan)
        return [(r.address, r.resource_type) for r in resources]

    def analyze(self, plan_path: Path) -> list[AnalysisMatch]:
        """Analyze a terraform plan for potential issues based on past fixes."""
        plan = self.load_plan(plan_path)
        resources = self.extract_resources(plan)
        matches = []

        for resource in resources:
            for fix in self.repo.find_by_resource_type(resource.resource_type):
                matches.append(
                    AnalysisMatch(
                        resource_address=resource.address,
                        resource_type=resource.resource_type,
                        related_fix=fix,
                        cloud_provider=resource.cloud_provider,
                    )
                )

        return matches

    def analyze_and_format(self, plan_path: Path) -> str:
        """Analyze a plan and return formatted output."""
        matches = self.analyze(plan_path)

        if not matches:
            return "No known issues found for resources in this plan."

        # Group by cloud provider
        by_provider = {}
        for match in matches:
            provider = match.cloud_provider.value
            by_provider.setdefault(provider, []).append(match)

        lines = [
            f"Found {len(matches)} potential issue(s) based on your fix history:",
            "",
        ]

        for provider, provider_matches in by_provider.items():
            if provider != "unknown":
                lines.append(f"── {provider.upper()} ──")
                lines.append("")

            for match in provider_matches:
                lines.append(match.format_warning())
                lines.append("")

        lines.append("Run `fixdoc show <fix-id>` for full details on any fix.")
        return "\n".join(lines)

    def get_plan_summary(self, plan_path: Path) -> dict:
        """Get a summary of the plan resources by cloud provider and action."""
        plan = self.load_plan(plan_path)
        resources = self.extract_resources(plan)

        summary = {
            "total": len(resources),
            "by_provider": {},
            "by_action": {},
            "by_type": {},
        }

        for r in resources:
            provider = r.cloud_provider.value
            summary["by_provider"][provider] = summary["by_provider"].get(provider, 0) + 1
            summary["by_action"][r.action] = summary["by_action"].get(r.action, 0) + 1
            summary["by_type"][r.resource_type] = summary["by_type"].get(r.resource_type, 0) + 1

        return summary


@click.command()
@click.argument("plan_file", type=click.Path(exists=True))
@click.option("--summary", "-s", is_flag=True, help="Show plan summary instead of analysis")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def analyze(plan_file: str, summary: bool, verbose: bool):
    """
    Analyze a terraform plan for issues.

    \b
    Usage:
        terraform plan -out=plan.tfplan
        terraform show -json plan.tfplan > plan.json
        fixdoc analyze plan.json

    \b
    Options:
        --summary    Show resource summary by provider/action
        --verbose    Show detailed match information
    """
    analyzer = TerraformAnalyzer()
    plan_path = Path(plan_file)

    try:
        if summary:
            # Show plan summary
            plan_summary = analyzer.get_plan_summary(plan_path)
            click.echo(f"Plan Summary: {plan_summary['total']} resources\n")

            if plan_summary['by_provider']:
                click.echo("By Provider:")
                for provider, count in sorted(plan_summary['by_provider'].items()):
                    click.echo(f"  {provider}: {count}")
                click.echo()

            if plan_summary['by_action']:
                click.echo("By Action:")
                for action, count in sorted(plan_summary['by_action'].items()):
                    click.echo(f"  {action}: {count}")
                click.echo()

            if verbose and plan_summary['by_type']:
                click.echo("By Resource Type:")
                for rtype, count in sorted(plan_summary['by_type'].items(), key=lambda x: -x[1]):
                    click.echo(f"  {rtype}: {count}")
        else:
            # Show analysis
            output = analyzer.analyze_and_format(plan_path)
            click.echo(output)

    except json.JSONDecodeError:
        click.echo(f"Error: {plan_file} is not valid JSON", err=True)
        click.echo("Make sure to use: terraform show -json plan.tfplan > plan.json", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Error analyzing plan: {e}", err=True)
        raise SystemExit(1)
