"""FixDoc - Capture and search infrastructure fixes for SRE/Devops engineers."""

__version__ = "0.1.0"

from .models import Fix
from .storage import FixRepository

__all__ = ["Fix", "FixRepository"]
