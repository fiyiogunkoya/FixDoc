"""Tests for markdown parsing (reverse of formatter)."""

import pytest

from fixdoc.models import Fix
from fixdoc.formatter import fix_to_markdown
from fixdoc.markdown_parser import markdown_to_fix, MarkdownParseError


class TestMarkdownParser:
    def test_round_trip_basic(self):
        """Test that Fix -> markdown -> Fix preserves data."""
        original = Fix(
            id="test-uuid-1234",
            issue="Storage account access denied",
            resolution="Added storage blob contributor role",
            created_at="2024-01-15T10:30:00+00:00",
            updated_at="2024-01-15T10:30:00+00:00",
        )

        markdown = fix_to_markdown(original)
        parsed = markdown_to_fix(markdown, original.id)

        assert parsed.issue == original.issue
        assert parsed.resolution == original.resolution
        assert parsed.created_at == original.created_at
        assert parsed.updated_at == original.updated_at

    def test_round_trip_with_all_fields(self):
        """Test round trip with all optional fields."""
        original = Fix(
            id="test-uuid-5678",
            issue="Key vault access policy missing",
            resolution="Added get and list secrets permissions",
            error_excerpt="AccessDenied: User is not authorized",
            tags="azurerm_key_vault,rbac",
            notes="Remember to check AAD permissions too",
            created_at="2024-01-15T10:30:00+00:00",
            updated_at="2024-01-16T14:00:00+00:00",
            author="John Doe",
            author_email="john@example.com",
        )

        markdown = fix_to_markdown(original)
        parsed = markdown_to_fix(markdown, original.id)

        assert parsed.issue == original.issue
        assert parsed.resolution == original.resolution
        assert parsed.error_excerpt == original.error_excerpt
        assert parsed.tags == original.tags
        assert parsed.notes == original.notes
        assert parsed.author == original.author
        assert parsed.author_email == original.author_email

    def test_parse_missing_issue_raises_error(self):
        """Test that missing Issue section raises error."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Resolution

Some resolution text
"""
        with pytest.raises(MarkdownParseError, match="Missing required 'Issue' section"):
            markdown_to_fix(markdown, "test-id")

    def test_parse_missing_resolution_raises_error(self):
        """Test that missing Resolution section raises error."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Issue

Some issue text
"""
        with pytest.raises(MarkdownParseError, match="Missing required 'Resolution' section"):
            markdown_to_fix(markdown, "test-id")

    def test_parse_multiline_issue(self):
        """Test parsing multiline issue text."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Issue

This is a multiline issue.
It spans multiple lines.
And has different paragraphs.

## Resolution

Fixed it.
"""
        parsed = markdown_to_fix(markdown, "test-id")

        assert "multiline issue" in parsed.issue
        assert "multiple lines" in parsed.issue

    def test_parse_code_block_in_error_excerpt(self):
        """Test parsing code block in Error Excerpt section."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Issue

Some issue

## Resolution

Some resolution

## Error Excerpt

```
Error: AuthorizationFailed
  User does not have permission
  Code: 403
```
"""
        parsed = markdown_to_fix(markdown, "test-id")

        assert "AuthorizationFailed" in parsed.error_excerpt
        assert "403" in parsed.error_excerpt

    def test_parse_tags_with_backticks(self):
        """Test parsing tags in backtick format."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

**Tags:** `storage,rbac,azure`

## Issue

Some issue

## Resolution

Some resolution
"""
        parsed = markdown_to_fix(markdown, "test-id")

        assert parsed.tags == "storage,rbac,azure"

    def test_parse_without_optional_sections(self):
        """Test parsing markdown without optional sections."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Issue

Minimal issue description

## Resolution

Minimal resolution
"""
        parsed = markdown_to_fix(markdown, "test-id")

        assert parsed.issue == "Minimal issue description"
        assert parsed.resolution == "Minimal resolution"
        assert parsed.error_excerpt is None
        assert parsed.tags is None
        assert parsed.notes is None

    def test_preserves_fix_id(self):
        """Test that the provided fix ID is used."""
        markdown = """# Fix: abc12345

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Issue

Test issue

## Resolution

Test resolution
"""
        parsed = markdown_to_fix(markdown, "full-uuid-from-filename")

        assert parsed.id == "full-uuid-from-filename"
