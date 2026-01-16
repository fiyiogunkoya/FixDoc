"""Markdown formatting for fixes."""

from .models import Fix


def fix_to_markdown(fix: Fix) -> str:
    """Generate markdown documentation for a fix."""
    lines = [
        f"# Fix: {fix.id[:8]}",
        "",
        f"**Created:** {fix.created_at}",
        f"**Updated:** {fix.updated_at}",
        "",
    ]

    if fix.tags:
        lines.extend([f"**Tags:** `{fix.tags}`", ""])

    lines.extend(
        [
            "## Issue",
            "",
            fix.issue,
            "",
            "## Resolution",
            "",
            fix.resolution,
            "",
        ]
    )

    if fix.error_excerpt:
        lines.extend(
            [
                "## Error Excerpt",
                "",
                "```",
                fix.error_excerpt,
                "```",
                "",
            ]
        )

    if fix.notes:
        lines.extend(
            [
                "## Notes",
                "",
                fix.notes,
                "",
            ]
        )

    return "\n".join(lines)
