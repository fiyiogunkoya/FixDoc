"""Fix data model for fixdoc."""

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import uuid


def _now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_for_hash(text: str) -> str:
    """Normalize text for content hashing: strip, collapse whitespace, lowercase."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def compute_content_hash(issue: str, resolution: str) -> str:
    """Compute a 16-char hex SHA-256 hash of normalized issue + resolution."""
    normalized = _normalize_for_hash(issue) + "\n" + _normalize_for_hash(resolution)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Fix:
    """
    Represents a fix.

    Required fields: issue, resolution
    Optional fields: error_excerpt, tags, notes, author, author_email
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
    author: Optional[str] = None
    author_email: Optional[str] = None
    is_private: bool = False
    source_error_ids: Optional[list] = None
    applied_count: int = 0
    success_count: int = 0
    last_applied_at: Optional[str] = None
    memory_type: str = "fix"
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = compute_content_hash(self.issue, self.resolution)

    @property
    def effectiveness_rate(self) -> Optional[float]:
        """Return success_count / applied_count, or None if never applied."""
        if self.applied_count == 0:
            return None
        return self.success_count / self.applied_count

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
            author=data.get("author"),
            author_email=data.get("author_email"),
            is_private=data.get("is_private", False),
            source_error_ids=data.get("source_error_ids"),
            applied_count=data.get("applied_count", 0),
            success_count=data.get("success_count", 0),
            last_applied_at=data.get("last_applied_at"),
            memory_type=data.get("memory_type", "fix"),
            content_hash=data.get("content_hash", ""),
        )

    def summary(self) -> str:
        """Return a one-line summary for list displays."""
        short_id = self.id[:8]
        tags_str = f" [{self.tags}]" if self.tags else ""
        issue_preview = self.issue[:40] + "..." if len(self.issue) > 40 else self.issue
        return f"{short_id}{tags_str} - {issue_preview}"

    def matches(self, query: str, match_any: bool = False) -> bool:
        """Check if this fix matches a search query (case-insensitive).

        By default uses AND matching: all words in the query must appear.
        With match_any=True, uses OR matching: any word suffices.
        """
        searchable = " ".join(
            filter(
                None,
                [self.issue, self.resolution, self.error_excerpt, self.tags, self.notes],
            )
        ).lower()
        words = query.lower().split()
        if not words:
            return False
        if match_any:
            return any(w in searchable for w in words)
        return all(w in searchable for w in words)

    def matches_tags(self, required_tags: list[str], match_any: bool = False) -> bool:
        """Check if this fix has the required tags.

        By default uses AND: all required_tags must be present.
        With match_any=True, uses OR: any tag suffices.
        """
        if not self.tags:
            return False
        fix_tags = {t.strip().lower() for t in self.tags.split(",") if t.strip()}
        required = {t.strip().lower() for t in required_tags if t.strip()}
        if not required:
            return True
        if match_any:
            return bool(fix_tags & required)
        return required.issubset(fix_tags)

    def matches_resource_type(self, resource_type: str) -> bool:
        """Check if this fix is tagged with a specific resource type."""
        if not self.tags:
            return False
        return resource_type.lower() in self.tags.lower()

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = _now_iso()
