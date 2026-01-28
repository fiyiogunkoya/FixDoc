"""CLI commands for fixdoc."""

from .capture import capture
from .search import search, show
from .analyze import analyze
from .manage import list_fixes, stats
from .delete import delete
from .edit import edit
from .sync import sync

__all__ = ["capture", "search", "show", "analyze", "list_fixes", "stats", "delete", "edit", "sync"]
