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
]

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
    model: str = "claude-sonnet-4-5-20241022",
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

    truncated = release_notes[:4000]

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
        "description, consequence, detection_hints (list), tags (list).\n"
        "- detection_hints should have: field, pattern (regex), reason, impact.\n"
        "- Include pre_checks and post_checks lists.\n"
        "- Generate a meaningful display_name.\n"
        "- Use severity conservatively: critical only for data loss or security issues.\n"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2000,
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
