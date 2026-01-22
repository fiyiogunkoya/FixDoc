"""Fix data model for fixdoc."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import uuid


def _now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Fix:
    """
    Represents a fix.

    Required fields: issue, resolution
    Optional fields: error_excerpt, tags, notes
    Auto-generated: id, created_at, updated_at
    """

    issue: str
    resolution: str
    error_excerpt: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        """Convert fix to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Fix":
        """Create a Fix instance from a dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            issue=data["issue"],
            resolution=data["resolution"],
            error_excerpt=data.get("error_excerpt"),
            tags=data.get("tags"),
            notes=data.get("notes"),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )

    def summary(self) -> str:
        """Return a one-line summary for list displays."""
        short_id = self.id[:8]
        tags_str = f" [{self.tags}]" if self.tags else ""
        issue_preview = self.issue[:40] + "..." if len(self.issue) > 40 else self.issue
        return f"{short_id}{tags_str} - {issue_preview}"

    def matches(self, query: str) -> bool:
        """Check if this fix matches a search query (case-insensitive)."""
        query_lower = query.lower()
        searchable = " ".join(
            filter(
                None,
                [self.issue, self.resolution, self.error_excerpt, self.tags, self.notes],
            )
        ).lower()
        return query_lower in searchable

    def matches_resource_type(self, resource_type: str) -> bool:
        """Check if this fix is tagged with a specific resource type."""
        if not self.tags:
            return False
        return resource_type.lower() in self.tags.lower()

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = _now_iso()
