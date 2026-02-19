"""Pending error storage for fixdoc.

Manages a per-project .fixdoc-pending JSON file at the git root,
allowing users to defer error capture for later.
"""

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class PendingEntry:
    """A deferred error awaiting capture."""

    error_id: str
    error_type: str  # "terraform" / "kubernetes" / etc.
    short_message: str
    error_excerpt: str
    tags: str
    deferred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resource_address: Optional[str] = None
    error_code: Optional[str] = None
    file: Optional[str] = None
    command: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PendingEntry":
        return cls(
            error_id=data["error_id"],
            error_type=data["error_type"],
            short_message=data["short_message"],
            error_excerpt=data["error_excerpt"],
            tags=data.get("tags", ""),
            deferred_at=data.get("deferred_at", ""),
            resource_address=data.get("resource_address"),
            error_code=data.get("error_code"),
            file=data.get("file"),
            command=data.get("command"),
        )


def pending_entry_from_parsed_error(err, command: Optional[str] = None) -> PendingEntry:
    """Create a PendingEntry from a ParsedError."""
    return PendingEntry(
        error_id=err.error_id,
        error_type=err.error_type,
        short_message=err.short_error(max_length=120),
        error_excerpt=err.raw_output[:2000],
        tags=err.generate_tags(),
        resource_address=err.resource_address,
        error_code=err.error_code,
        file=f"{err.file}:{err.line}" if err.file and err.line else err.file,
        command=command,
    )


def _find_git_root(start: Optional[Path] = None) -> Path:
    """Find the git root directory, falling back to CWD."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(start) if start else None,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except FileNotFoundError:
        pass
    return start or Path.cwd()


class PendingStore:
    """Manages the .fixdoc-pending JSON file."""

    FILENAME = ".fixdoc-pending"

    def __init__(self, project_dir: Optional[Path] = None):
        root = _find_git_root(project_dir)
        self._pending_path = root / self.FILENAME

    @property
    def path(self) -> Path:
        return self._pending_path

    def _read(self) -> list[dict]:
        if not self._pending_path.exists():
            return []
        try:
            data = json.loads(self._pending_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write(self, entries: list[dict]) -> None:
        self._pending_path.write_text(
            json.dumps(entries, indent=2) + "\n", encoding="utf-8"
        )

    def save(self, entry: PendingEntry) -> None:
        """Append a pending entry (replaces if same error_id exists)."""
        entries = self._read()
        # Replace existing entry with same error_id
        entries = [e for e in entries if e.get("error_id") != entry.error_id]
        entries.append(entry.to_dict())
        self._write(entries)

    def list_all(self) -> list[PendingEntry]:
        """Return all pending entries."""
        return [PendingEntry.from_dict(e) for e in self._read()]

    def remove(self, error_id: str) -> bool:
        """Remove a pending entry by error_id (or prefix). Returns True if found."""
        entries = self._read()
        original_len = len(entries)
        entries = [
            e for e in entries
            if not e.get("error_id", "").startswith(error_id)
        ]
        if len(entries) < original_len:
            self._write(entries)
            return True
        return False

    def clear(self) -> int:
        """Remove all pending entries. Returns count removed."""
        entries = self._read()
        count = len(entries)
        if count > 0:
            self._write([])
        return count

    def get(self, error_id: str) -> Optional[PendingEntry]:
        """Get a pending entry by error_id or prefix."""
        for entry in self.list_all():
            if entry.error_id.startswith(error_id):
                return entry
        return None
