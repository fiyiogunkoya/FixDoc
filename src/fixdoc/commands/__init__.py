"""CLI commands for fixdoc."""

from .capture import capture
from .search import search, show
from .analyze import analyze
from .manage import list_fixes, stats
from .delete import delete
from .edit import edit
from .sync import sync
from .demo import demo
from .watch import watch
from .blast_radius import blast_radius

__all__ = ["capture", "search", "show", "analyze", "list_fixes", "stats", "delete", "edit", "sync", "demo", "watch", "blast_radius"]
