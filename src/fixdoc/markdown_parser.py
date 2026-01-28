"""Markdown parsing for fixes - reverse of formatter.py."""

import re
from typing import Optional

from .models import Fix


class MarkdownParseError(Exception):
    """Raised when markdown parsing fails."""

    pass


def markdown_to_fix(content: str, fix_id: str) -> Fix:
    """
    Parse markdown content back into a Fix object.

    Expected format matches output of fix_to_markdown():
    - Header: # Fix: {short_id}
    - Metadata: **Created:** ... **Updated:** ... **Author:** ...
    - Sections: ## Issue, ## Resolution, ## Error Excerpt, ## Notes
    """
    created_at = _extract_metadata(content, "Created")
    updated_at = _extract_metadata(content, "Updated")
    author = _extract_metadata(content, "Author")
    author_email = _extract_metadata(content, "Author Email")
    tags = _extract_tags(content)

    issue = _extract_section(content, "Issue")
    resolution = _extract_section(content, "Resolution")
    error_excerpt = _extract_code_block(content, "Error Excerpt")
    notes = _extract_section(content, "Notes")

    if not issue:
        raise MarkdownParseError("Missing required 'Issue' section")
    if not resolution:
        raise MarkdownParseError("Missing required 'Resolution' section")

    return Fix(
        id=fix_id,
        issue=issue,
        resolution=resolution,
        error_excerpt=error_excerpt,
        tags=tags,
        notes=notes,
        created_at=created_at or "",
        updated_at=updated_at or "",
        author=author,
        author_email=author_email,
    )


def _extract_metadata(content: str, field: str) -> Optional[str]:
    """Extract **Field:** value from content."""
    pattern = rf"\*\*{re.escape(field)}:\*\*\s*(.+?)(?:\n|$)"
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return None


def _extract_tags(content: str) -> Optional[str]:
    """Extract **Tags:** `value` from content."""
    pattern = r"\*\*Tags:\*\*\s*`([^`]+)`"
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return None


def _extract_section(content: str, section_name: str) -> Optional[str]:
    """Extract content under ## SectionName header."""
    pattern = rf"##\s+{re.escape(section_name)}\s*\n\n?(.*?)(?=\n##\s|\n\*\*|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        text = match.group(1).strip()
        if text.startswith("```"):
            return None
        return text if text else None
    return None


def _extract_code_block(content: str, section_name: str) -> Optional[str]:
    """Extract code block content from a section."""
    pattern = rf"##\s+{re.escape(section_name)}\s*\n\n?```[^\n]*\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def parse_markdown_file(file_path: str) -> Fix:
    """Parse a markdown file and return a Fix object."""
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        raise MarkdownParseError(f"File not found: {file_path}")

    fix_id = path.stem

    with open(path, "r") as f:
        content = f.read()

    return markdown_to_fix(content, fix_id)
