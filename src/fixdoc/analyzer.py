"""Terraform plan analyzer for fixdoc."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import Fix
from .storage import FixRepository


@dataclass
class AnalysisMatch:
    """Represents a potential issue found during terraform plan analysis."""

    resource_address: str
    resource_type: str
    related_fix: Fix

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


class TerraformAnalyzer:
    """Analyzes terraform plan JSON output against known fixes."""

    def __init__(self, repo: Optional[FixRepository] = None):
        self.repo = repo or FixRepository()

    def load_plan(self, plan_path: Path) -> dict:
        """Load and parse a terraform plan JSON file."""
        with open(plan_path, "r") as f:
            return json.load(f)

    def extract_resource_types(self, plan: dict) -> list[tuple[str, str]]:
        """Extract (resource_address, resource_type) tuples from a plan."""
        resources = []

        for change in plan.get("resource_changes", []):
            address = change.get("address", "")
            resource_type = change.get("type", "")
            if resource_type:
                resources.append((address, resource_type))

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for addr, rtype in resources:
            if (addr, rtype) not in seen:
                seen.add((addr, rtype))
                unique.append((addr, rtype))

        return unique

    def analyze(self, plan_path: Path) -> list[AnalysisMatch]:
        """Analyze a terraform plan for potential issues based on past fixes."""
        plan = self.load_plan(plan_path)
        resources = self.extract_resource_types(plan)
        matches = []

        for address, resource_type in resources:
            for fix in self.repo.find_by_resource_type(resource_type):
                matches.append(
                    AnalysisMatch(
                        resource_address=address,
                        resource_type=resource_type,
                        related_fix=fix,
                    )
                )

        return matches

    def analyze_and_format(self, plan_path: Path) -> str:
        """Analyze a plan and return formatted output."""
        matches = self.analyze(plan_path)

        if not matches:
            return "No known issues found for resources in this plan."

        lines = [
            f"Found {len(matches)} potential issue(s) based on your fix history:",
            "",
        ]

        for match in matches:
            lines.append(match.format_warning())
            lines.append("")

        lines.append("Run `fixdoc show <fix-id>` for full details on any fix.")
        return "\n".join(lines)
