"""Blast radius command module — merged into analyze.

The change impact engine lives at src/fixdoc/change_impact.py.
The CLI command is now part of `fixdoc analyze`.
This module is kept empty to avoid import errors in tests that
reference it directly.

Backward-compat shim: re-exports from change_impact.
"""

from ..change_impact import (  # noqa: F401
    ImpactNode as BlastNode,
    ImpactResult as BlastResult,
    analyze_change_impact as analyze_blast_radius,
    compute_impact_score as compute_blast_score,
)
