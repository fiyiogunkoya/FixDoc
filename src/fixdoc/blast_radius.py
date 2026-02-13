"""Blast radius analysis engine for fixdoc.

Estimates which identities, workloads, and resources are most likely
affected by infrastructure changes before they're applied. Combines
Terraform plan JSON, the terraform graph dependency DAG, and FixDoc's
fix history into a weighted BlastScore (0-100) with explainable
propagation paths.
"""

import math
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .storage import FixRepository

# ---------------------------------------------------------------------------
# Control-point classification
# ---------------------------------------------------------------------------

# Maps resource type prefix -> (category, criticality 0-1)
CONTROL_POINT_PATTERNS: dict[str, tuple[str, float]] = {
    # AWS IAM
    "aws_iam_role_policy_attachment": ("iam", 0.9),
    "aws_iam_role_policy": ("iam", 0.9),
    "aws_iam_policy_attachment": ("iam", 0.9),
    "aws_iam_group_policy_attachment": ("iam", 0.85),
    "aws_iam_user_policy_attachment": ("iam", 0.85),
    "aws_iam_role": ("iam", 0.9),
    "aws_iam_policy": ("iam", 0.85),
    "aws_iam_user": ("iam", 0.8),
    "aws_iam_group": ("iam", 0.75),
    # Azure RBAC
    "azurerm_role_assignment": ("rbac", 0.9),
    "azurerm_key_vault_access_policy": ("rbac", 0.85),
    "azurerm_role_definition": ("rbac", 0.85),
    # GCP IAM
    "google_project_iam": ("iam", 0.9),
    "google_service_account": ("iam", 0.85),
    # Network boundaries
    "aws_security_group": ("network", 0.8),
    "aws_network_acl": ("network", 0.8),
    "aws_route_table": ("network", 0.7),
    "azurerm_network_security_group": ("network", 0.8),
    "azurerm_firewall_rule": ("network", 0.85),
    "google_compute_firewall": ("network", 0.8),
}

# Sensitive value patterns for redaction
SENSITIVE_PATTERNS = re.compile(
    r"(password|secret|token|api_key|private_key|access_key|credentials)",
    re.IGNORECASE,
)

# Recommended checks per control-point category
CATEGORY_CHECKS: dict[str, list[str]] = {
    "iam": [
        "Review IAM policy least-privilege before applying",
        "Check service account permissions",
    ],
    "rbac": [
        "Review RBAC role assignment scope",
        "Verify key vault access policy changes",
    ],
    "network": [
        "Verify security group rules",
        "Check for open 0.0.0.0/0 rules",
    ],
}

DELETE_CHECKS = ["Confirm resource is not referenced by other stacks"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BlastNode:
    """A resource node in the blast radius graph."""

    address: str
    resource_type: str
    action: str  # create, update, delete, no-op
    cloud_provider: str = "unknown"
    is_control_point: bool = False
    criticality: float = 0.0
    category: str = ""


@dataclass
class AffectedResource:
    """A resource reached by BFS propagation from a control point."""

    address: str
    resource_type: str
    depth: int
    path: list[str] = field(default_factory=list)


@dataclass
class BlastResult:
    """Complete result of a blast radius analysis."""

    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    score: float = 0.0
    severity: str = "low"
    changes: list[dict] = field(default_factory=list)
    control_points: list[dict] = field(default_factory=list)
    affected: list[dict] = field(default_factory=list)
    why_paths: list[dict] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    history_matches: list[dict] = field(default_factory=list)
    plan_summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Control-point classification
# ---------------------------------------------------------------------------


def classify_control_point(resource_type: str) -> Optional[tuple[str, float]]:
    """Classify a resource type as a control point.

    Uses prefix matching so e.g. 'google_project_iam_member' matches
    'google_project_iam'.

    Returns (category, criticality) or None if not a control point.
    """
    rt_lower = resource_type.lower()
    # Try longest prefix first so more specific patterns win
    best_match = None
    best_len = 0
    for prefix, (category, criticality) in CONTROL_POINT_PATTERNS.items():
        if rt_lower.startswith(prefix) and len(prefix) > best_len:
            best_match = (category, criticality)
            best_len = len(prefix)
    return best_match


# ---------------------------------------------------------------------------
# DOT graph parser
# ---------------------------------------------------------------------------

# Matches edges: "node_a" -> "node_b" or unquoted node_a -> node_b
_EDGE_RE = re.compile(
    r'"([^"]+)"\s*->\s*"([^"]+)"'
    r"|"
    r"(\S+)\s*->\s*(\S+)"
)


def _normalize_tf_node(name: str) -> str:
    """Normalize a Terraform graph node name to match plan addresses.

    Strips '[root] ' prefix and '(expand)'/'(close)' suffixes.
    """
    name = name.strip()
    if name.startswith("[root] "):
        name = name[7:]
    name = re.sub(r"\s*\(expand\)\s*$", "", name)
    name = re.sub(r"\s*\(close\)\s*$", "", name)
    return name.strip()


def parse_dot_graph(dot_text: str) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Parse a Terraform DOT graph into forward and reverse adjacency lists.

    Returns (forward_adj, reverse_adj) where forward means A -> B
    (A depends on B or B is downstream of A, depending on TF graph direction).
    """
    forward: dict[str, set[str]] = {}
    reverse: dict[str, set[str]] = {}

    for line in dot_text.splitlines():
        stripped = line.strip()
        # Skip comments, subgraph declarations, closing braces
        if (
            stripped.startswith("//")
            or stripped.startswith("#")
            or stripped.startswith("subgraph")
            or stripped.startswith("digraph")
            or stripped in ("}", "{")
        ):
            continue

        m = _EDGE_RE.search(stripped)
        if m:
            if m.group(1) is not None:
                src = _normalize_tf_node(m.group(1))
                dst = _normalize_tf_node(m.group(2))
            else:
                src = _normalize_tf_node(m.group(3))
                dst = _normalize_tf_node(m.group(4))

            forward.setdefault(src, set()).add(dst)
            forward.setdefault(dst, set())
            reverse.setdefault(dst, set()).add(src)
            reverse.setdefault(src, set())

    return forward, reverse


# ---------------------------------------------------------------------------
# Bounded BFS
# ---------------------------------------------------------------------------


def compute_affected_set(
    start_nodes: list[str],
    adjacency: dict[str, set[str]],
    max_depth: int = 5,
) -> list[AffectedResource]:
    """BFS from start_nodes through adjacency, bounded by max_depth.

    Returns list of AffectedResource with traversal paths.
    Keeps shortest path when reached from multiple starts.
    """
    visited: dict[str, AffectedResource] = {}
    queue: deque[tuple[str, int, list[str]]] = deque()

    for node in start_nodes:
        queue.append((node, 0, [node]))
        visited[node] = AffectedResource(
            address=node, resource_type="", depth=0, path=[node]
        )

    while queue:
        current, depth, path = queue.popleft()
        if depth >= max_depth:
            continue

        for neighbor in adjacency.get(current, set()):
            if neighbor not in visited:
                new_path = path + [neighbor]
                visited[neighbor] = AffectedResource(
                    address=neighbor,
                    resource_type="",
                    depth=depth + 1,
                    path=new_path,
                )
                queue.append((neighbor, depth + 1, new_path))

    # Remove start nodes from results (they are the changes, not affected)
    return [ar for ar in visited.values() if ar.address not in start_nodes]


# ---------------------------------------------------------------------------
# Blast score formula
# ---------------------------------------------------------------------------

# Hardcoded coefficients
_A = 1.5   # affected-count weight
_B = 2.0   # criticality weight
_C = 1.8   # change-action weight
_D = 1.0   # history-prior weight
_OFFSET = 3.0  # centering offset

_ACTION_WEIGHTS = {
    "delete": 1.0,
    "update": 0.7,
    "create": 0.4,
    "no-op": 0.0,
    "unknown": 0.3,
}


def _sigmoid(x: float) -> float:
    """Standard sigmoid function."""
    return 1.0 / (1.0 + math.exp(-x))


def compute_blast_score(
    affected_count: int,
    max_criticality: float,
    actions: list[str],
    history_prior: float,
) -> float:
    """Compute blast score 0-100.

    BlastScore = 100 * sigmoid(a*ln(1+R) + b*C + c*delta + d*H - offset)
    """
    r = affected_count
    c = max_criticality
    delta = max((_ACTION_WEIGHTS.get(a, 0.3) for a in actions), default=0.0)
    h = history_prior

    raw = _A * math.log(1 + r) + _B * c + _C * delta + _D * h - _OFFSET
    return round(100.0 * _sigmoid(raw), 1)


def severity_label(score: float) -> str:
    """Map blast score to severity label."""
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# History-prior scoring
# ---------------------------------------------------------------------------


def compute_history_prior(
    changed_resource_types: list[str],
    repo: FixRepository,
) -> tuple[float, list[dict]]:
    """Compute history prior from fix database.

    Returns (prior_0_to_1, list_of_matching_fix_dicts).
    """
    all_matches = []
    seen_ids: set[str] = set()

    for rt in changed_resource_types:
        for fix in repo.find_by_resource_type(rt):
            if fix.id not in seen_ids:
                seen_ids.add(fix.id)
                all_matches.append(
                    {
                        "id": fix.id[:8],
                        "issue": fix.issue,
                        "resource_type": rt,
                    }
                )

    prior = min(1.0, len(all_matches) / 3.0)
    return prior, all_matches


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def redact_plan_values(change_block: dict) -> dict:
    """Redact sensitive values from a plan change block.

    1. Honors sensitive_values markers from the plan JSON.
    2. Pattern-matches keys against SENSITIVE_PATTERNS.
    3. Replaces values with '[REDACTED]'.
    """
    result = {}
    sensitive_keys = set()

    # Collect keys flagged by Terraform's sensitive_values
    for phase in ("before_sensitive", "after_sensitive"):
        sv = change_block.get(phase)
        if isinstance(sv, dict):
            _collect_sensitive_keys(sv, "", sensitive_keys)

    for key, value in change_block.items():
        if key in ("before_sensitive", "after_sensitive"):
            continue
        if isinstance(value, dict):
            result[key] = _redact_dict(value, sensitive_keys, "")
        else:
            result[key] = value

    return result


def _collect_sensitive_keys(
    sensitive_map: dict, prefix: str, out: set[str]
) -> None:
    """Recursively collect keys marked as sensitive."""
    for key, val in sensitive_map.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if val is True:
            out.add(full_key)
        elif isinstance(val, dict):
            _collect_sensitive_keys(val, full_key, out)


def _redact_dict(
    d: dict, sensitive_keys: set[str], prefix: str
) -> dict:
    """Recursively redact sensitive values in a dict."""
    result = {}
    for key, val in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if full_key in sensitive_keys or SENSITIVE_PATTERNS.search(key):
            result[key] = "[REDACTED]"
        elif isinstance(val, dict):
            result[key] = _redact_dict(val, sensitive_keys, full_key)
        else:
            result[key] = val
    return result


# ---------------------------------------------------------------------------
# Recommended checks generator
# ---------------------------------------------------------------------------


def generate_checks(
    control_points: list[BlastNode],
    has_deletes: bool,
) -> list[str]:
    """Generate recommended checks based on control point categories."""
    checks: list[str] = []
    seen_categories: set[str] = set()

    for cp in control_points:
        if cp.category and cp.category not in seen_categories:
            seen_categories.add(cp.category)
            checks.extend(CATEGORY_CHECKS.get(cp.category, []))

    if has_deletes:
        checks.extend(DELETE_CHECKS)

    return checks


# ---------------------------------------------------------------------------
# Main analysis orchestrator
# ---------------------------------------------------------------------------


def analyze_blast_radius(
    plan: dict,
    repo: FixRepository,
    dot_text: Optional[str] = None,
    max_depth: int = 5,
) -> BlastResult:
    """Run a full blast radius analysis on a Terraform plan.

    Args:
        plan: Parsed Terraform plan JSON.
        repo: FixRepository for history lookup.
        dot_text: Optional DOT graph text from `terraform graph`.
        max_depth: Max BFS traversal depth.

    Returns:
        BlastResult with score, severity, affected resources, etc.
    """
    from .commands.analyze import TerraformAnalyzer

    analyzer = TerraformAnalyzer(repo=repo)
    resources = analyzer.extract_resources(plan)

    # Build nodes and identify control points
    nodes: list[BlastNode] = []
    control_points: list[BlastNode] = []
    changes: list[dict] = []

    for res in resources:
        if res.action == "no-op":
            continue

        cp_info = classify_control_point(res.resource_type)
        is_cp = cp_info is not None
        category = cp_info[0] if cp_info else ""
        criticality = cp_info[1] if cp_info else 0.0

        node = BlastNode(
            address=res.address,
            resource_type=res.resource_type,
            action=res.action,
            cloud_provider=res.cloud_provider.value,
            is_control_point=is_cp,
            criticality=criticality,
            category=category,
        )
        nodes.append(node)

        if is_cp:
            control_points.append(node)

        changes.append(
            {
                "address": res.address,
                "resource_type": res.resource_type,
                "action": res.action,
                "cloud_provider": res.cloud_provider.value,
                "is_control_point": is_cp,
                "category": category,
                "criticality": criticality,
            }
        )

    # BFS propagation if graph is available
    affected: list[AffectedResource] = []
    if dot_text and control_points:
        forward, reverse = parse_dot_graph(dot_text)
        # Use both directions — control point changes can affect dependents
        combined: dict[str, set[str]] = {}
        for adj in (forward, reverse):
            for k, v in adj.items():
                combined.setdefault(k, set()).update(v)

        start_addrs = [cp.address for cp in control_points]
        affected = compute_affected_set(start_addrs, combined, max_depth)

    # History prior
    changed_types = list({n.resource_type for n in nodes})
    history_prior, history_matches = compute_history_prior(changed_types, repo)

    # Blast score
    actions = [n.action for n in nodes]
    max_crit = max((cp.criticality for cp in control_points), default=0.0)
    score = compute_blast_score(len(affected), max_crit, actions, history_prior)
    sev = severity_label(score)

    # Recommended checks
    has_deletes = any(n.action == "delete" for n in nodes)
    checks = generate_checks(control_points, has_deletes)

    # Build why-paths for affected resources
    why_paths = []
    for ar in affected[:20]:  # Cap at 20 for readability
        why_paths.append(
            {
                "target": ar.address,
                "depth": ar.depth,
                "path": ar.path,
            }
        )

    # Plan summary
    plan_summary = {
        "total_changes": len(nodes),
        "control_points": len(control_points),
        "affected_resources": len(affected),
        "by_action": {},
    }
    for n in nodes:
        plan_summary["by_action"][n.action] = (
            plan_summary["by_action"].get(n.action, 0) + 1
        )

    return BlastResult(
        score=score,
        severity=sev,
        changes=changes,
        control_points=[
            {
                "address": cp.address,
                "resource_type": cp.resource_type,
                "action": cp.action,
                "category": cp.category,
                "criticality": cp.criticality,
            }
            for cp in control_points
        ],
        affected=[
            {
                "address": ar.address,
                "depth": ar.depth,
                "path": ar.path,
            }
            for ar in affected
        ],
        why_paths=why_paths,
        checks=checks,
        history_matches=history_matches,
        plan_summary=plan_summary,
    )


def _find_change_block(plan: dict, address: str) -> Optional[dict]:
    """Find the change block for a resource address in the plan."""
    for change in plan.get("resource_changes", []):
        if change.get("address") == address:
            return change.get("change", {})
    return None
