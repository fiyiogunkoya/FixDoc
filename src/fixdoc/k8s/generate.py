"""AI-assisted catalog entry generation for fixdoc k8s.

Uses Claude API to extract breaking changes from release notes and
generate ready-to-commit YAML catalog entries.
"""

import os
from typing import Optional

import yaml

from .models import CatalogEntry


_VALID_HINT_FIELDS = [
    "images",
    "volumes",
    "security_context",
    "node_selector",
    "tolerations",
    "labels",
    "annotations",
    "resource_requests",
    "resource_limits",
    "ingress_class",
]

_VALID_APPLIES_TO_FIELDS = ["names", "namespaces", "labels", "images", "kinds"]

_EXAMPLE_ENTRY = """\
category: os-upgrade
from_version: "azurelinux:2.0"
to_version: "azurelinux:3.0"
display_name: "Azure Linux 2.0 to 3.0"
breaking_changes:
  - id: os-azl3-glibc
    title: "glibc 2.35 to 2.38"
    severity: critical
    description: >
      Azure Linux 3.0 ships glibc 2.38. Statically linked binaries
      compiled against glibc 2.35 may encounter symbol version mismatches.
    consequence: >
      Pods crash on startup with 'version GLIBC_2.36 not found'.
    detection_hints:
      - field: images
        pattern: "(distroless|scratch|alpine|static)"
        applies_to:
          kinds: [Deployment, StatefulSet]
        reason: "Container uses a minimal base image that may bundle old glibc-linked binaries"
        impact: "Binary may fail at runtime with glibc symbol errors"
    tags: [glibc, azurelinux]
pre_checks:
  - "Audit container base images for glibc version compatibility"
post_checks:
  - "Verify all pods reach Running state after upgrade"
tags: [azurelinux, os-upgrade]
"""


def generate_catalog_entry(
    category: str,
    from_version: str,
    to_version: str,
    release_notes: str,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-6",
) -> Optional[str]:
    """Generate a YAML catalog entry from release notes using Claude API.

    Returns YAML string, or None on failure.
    """
    try:
        import anthropic
    except ImportError:
        return None

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    truncated = release_notes[:12000]

    prompt = (
        "You are a Kubernetes platform engineer. Given the release notes below, "
        "extract breaking changes and generate a YAML catalog entry.\n\n"
        f"Category: {category}\n"
        f"From version: {from_version}\n"
        f"To version: {to_version}\n\n"
        "Release notes:\n"
        f"{truncated}\n\n"
        "Valid detection hint fields (use ONLY these): "
        f"{', '.join(_VALID_HINT_FIELDS)}\n\n"
        "Example of a well-formed entry:\n"
        f"{_EXAMPLE_ENTRY}\n\n"
        "Instructions:\n"
        "- Output ONLY valid YAML. No markdown fences, no commentary.\n"
        "- Each breaking change needs: id, title, severity (critical/high/medium/low), "
        "description (>20 chars), consequence (>10 chars), detection_hints (list), tags (list).\n"
        "- detection_hints should have: field, pattern (regex), reason, impact.\n"
        "- Use `applies_to` to scope hints that would otherwise match too broadly "
        "(e.g. resource_requests, resource_limits). Valid applies_to fields: "
        f"{', '.join(_VALID_APPLIES_TO_FIELDS)}. "
        "All sub-fields use AND logic; multiple values within a sub-field use OR logic.\n"
        "- Avoid trivially broad patterns like '.' or '.*' without applies_to scoping.\n"
        "- Include pre_checks and post_checks lists.\n"
        "- Generate a meaningful display_name.\n"
        "- Use severity conservatively: critical only for data loss or security issues.\n"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception:
        return None


def validate_generated_yaml(yaml_text: str) -> Optional[CatalogEntry]:
    """Parse generated YAML and validate as a CatalogEntry.

    Returns CatalogEntry on success, None on failure.
    """
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    if not all(k in data for k in ("category", "from_version", "to_version")):
        return None

    try:
        return CatalogEntry.from_dict(data)
    except (KeyError, TypeError):
        return None


def validate_generated_entry(entry: CatalogEntry) -> list:
    """Validate a generated CatalogEntry and return warning strings.

    Does not block usage — warnings inform the user to review.
    """
    import re

    warnings = []
    critical_count = 0

    for bc in entry.breaking_changes:
        bc_label = bc.id or bc.title or "unknown"

        if len(bc.description) <= 20:
            warnings.append(f"Breaking change '{bc_label}': description is too short ({len(bc.description)} chars, want >20)")

        if len(bc.consequence) <= 10:
            warnings.append(f"Breaking change '{bc_label}': consequence is too short ({len(bc.consequence)} chars, want >10)")

        if bc.severity == "critical":
            critical_count += 1

        if not bc.detection_hints:
            warnings.append(f"Breaking change '{bc_label}': has 0 detection hints")

        for i, hint in enumerate(bc.detection_hints):
            field = hint.get("field", "")
            if field and field not in _VALID_HINT_FIELDS:
                warnings.append(f"Breaking change '{bc_label}': hint {i+1} uses invalid field '{field}'")

            pattern = hint.get("pattern", "")
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    warnings.append(f"Breaking change '{bc_label}': hint {i+1} has invalid regex: {exc}")

            if pattern in (".", ".*", ".+", ".?") and not hint.get("applies_to"):
                warnings.append(f"Breaking change '{bc_label}': hint {i+1} has trivially broad pattern '{pattern}' without applies_to scoping")

            if not hint.get("reason"):
                warnings.append(f"Breaking change '{bc_label}': hint {i+1} missing 'reason'")

            if not hint.get("impact"):
                warnings.append(f"Breaking change '{bc_label}': hint {i+1} missing 'impact'")

    total = len(entry.breaking_changes)
    if total > 0 and critical_count > total / 2:
        warnings.append(f"{critical_count}/{total} breaking changes are 'critical' — consider if severity is inflated")

    return warnings
