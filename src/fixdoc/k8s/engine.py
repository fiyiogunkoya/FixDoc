"""Kubernetes change impact analysis engine."""

import json
import re
import uuid
from typing import Optional

from .catalog import resolve_change
from .models import (
    ClusterSnapshot,
    ExposedWorkload,
    K8sImpactResult,
    RolloutRisk,
    Workload,
    _now_iso,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHT = {"critical": 25, "high": 15, "medium": 8, "low": 3}

_CATEGORY_MULTIPLIER = {
    "os-upgrade": 1.0,
    "k8s-version": 0.9,
    "ingress-controller": 0.8,
    "node-pool-sku": 0.85,
}

_SEVERITY_BANDS = [
    (76, "critical"),
    (51, "high"),
    (26, "medium"),
    (0, "low"),
]

_RECOMMENDATION = {
    "low": "Low risk. Standard deployment practices are sufficient.",
    "medium": "Test in a non-production environment before proceeding.",
    "high": "Stage this change on a non-production node pool first.",
    "critical": "Block until critical risks are mitigated. See pre-migration checklist.",
}

# Tags used when querying fix database for relevant team knowledge
_K8S_SEARCH_TAGS = {
    "os-upgrade": ["azurelinux", "os-upgrade", "cgroup", "glibc", "aks", "kubernetes"],
    "k8s-version": ["kubernetes", "k8s", "api-deprecation", "kubelet", "aks"],
    "ingress-controller": ["ingress", "nginx", "contour", "envoy", "aks", "kubernetes"],
    "node-pool-sku": ["node-pool", "sku", "oom", "gpu", "aks", "kubernetes"],
}


# ---------------------------------------------------------------------------
# Workload matching
# ---------------------------------------------------------------------------


def _match_hint_against_workload(hint: dict, workload: Workload) -> bool:
    """Check if a detection hint matches a workload."""
    field_name = hint.get("field", "")
    pattern = hint.get("pattern", "")
    if not field_name or not pattern:
        return False

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False

    # Get the field value to test
    value = _get_workload_field_value(workload, field_name)
    if value is None:
        return False

    # Convert to searchable string
    if isinstance(value, (dict, list)):
        search_text = json.dumps(value)
    else:
        search_text = str(value)

    return bool(regex.search(search_text))


def _get_workload_field_value(workload: Workload, field_name: str):
    """Get a field value from a workload, supporting dot-path for spec_raw."""
    # Direct attributes first
    direct_fields = {
        "images": workload.images,
        "volumes": workload.volumes,
        "security_context": workload.security_context,
        "node_selector": workload.node_selector,
        "tolerations": workload.tolerations,
        "labels": workload.labels,
        "annotations": workload.annotations,
        "resource_requests": workload.resource_requests,
        "resource_limits": workload.resource_limits,
        "tls": None,  # only on IngressResource
    }

    if field_name in direct_fields:
        return direct_fields[field_name]

    # Fall back to spec_raw traversal
    return _traverse_spec(workload.spec_raw, field_name)


def _traverse_spec(spec: dict, path: str):
    """Traverse a spec dict using dot-path notation (e.g. 'spec.volumes')."""
    parts = path.split(".")
    current = spec
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            # Flatten: collect the field from all list items
            results = []
            for item in current:
                if isinstance(item, dict):
                    val = item.get(part)
                    if val is not None:
                        results.append(val)
            current = results if results else None
        else:
            return None
        if current is None:
            return None
    return current


def _match_hint_against_ingress(hint: dict, ingress) -> bool:
    """Check if a detection hint matches an ingress resource."""
    field_name = hint.get("field", "")
    pattern = hint.get("pattern", "")
    if not field_name or not pattern:
        return False

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False

    field_map = {
        "annotations": ingress.annotations,
        "rules": ingress.rules,
        "tls": ingress.tls,
    }

    value = field_map.get(field_name)
    if value is None:
        return False

    if isinstance(value, (dict, list)):
        search_text = json.dumps(value)
    else:
        search_text = str(value)

    return bool(regex.search(search_text))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _compute_baseline_score(breaking_changes: list, category: str) -> float:
    """Step 1: Baseline from breaking change severity weights."""
    total = sum(
        _SEVERITY_WEIGHT.get(bc.severity, 0) for bc in breaking_changes
    )
    multiplier = _CATEGORY_MULTIPLIER.get(category, 1.0)
    return min(total * multiplier, 70.0)


def _compute_exposure_score(exposed: list) -> float:
    """Step 2: Score from exposed workload types."""
    kind_weights = {"DaemonSet": 5, "StatefulSet": 4, "Deployment": 2, "Job": 1}
    total = 0.0
    for ew in exposed:
        wl = ew.workload if isinstance(ew, ExposedWorkload) else ew.get("workload", {})
        kind = wl.kind if isinstance(wl, Workload) else wl.get("kind", "Deployment")
        total += kind_weights.get(kind, 1)
    return min(total, 30.0)


def _severity_label(score: float) -> str:
    """Convert score to severity band."""
    for threshold, label in _SEVERITY_BANDS:
        if score >= threshold:
            return label
    return "low"


# ---------------------------------------------------------------------------
# Fix database integration
# ---------------------------------------------------------------------------


def _find_relevant_fixes(category: str, repo) -> list:
    """Query fix database for team knowledge relevant to this change type."""
    if repo is None:
        return []

    search_tags = _K8S_SEARCH_TAGS.get(category, ["kubernetes", "aks"])
    all_fixes = repo.list_all()
    relevant = []

    for fix in all_fixes:
        if fix.matches_tags(search_tags, match_any=True):
            relevant.append({
                "id": fix.id[:8],
                "issue": fix.issue,
                "resolution": fix.resolution,
                "tags": fix.tags,
            })

    return relevant[:10]  # cap at 10


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------


def analyze_k8s_change(
    category: str,
    from_version: str,
    to_version: str,
    snapshot: Optional[ClusterSnapshot] = None,
    repo=None,
    catalog: Optional[list] = None,
) -> K8sImpactResult:
    """Analyze the impact of a Kubernetes platform change.

    Args:
        category: Change category (os-upgrade, k8s-version, etc.)
        from_version: Source version
        to_version: Target version
        snapshot: Optional cluster snapshot for personalized analysis
        repo: Optional FixRepository for team knowledge lookup
        catalog: Optional merged catalog list (built-in + custom)

    Returns:
        K8sImpactResult with score, severity, and detailed findings
    """
    entry = resolve_change(category, from_version, to_version, catalog=catalog)

    if entry is None:
        return K8sImpactResult(
            change_name=f"{category}: {from_version} -> {to_version}",
            category=category,
            from_version=from_version,
            to_version=to_version,
            score=0.0,
            severity="low",
            recommendation=f"No catalog entry found for {category} {from_version} -> {to_version}.",
            score_explanation=[{"label": "No matching catalog entry", "delta": 0, "kind": "baseline"}],
        )

    breaking_changes = entry.breaking_changes
    has_cluster = snapshot is not None

    # --- Step 1: Baseline score ---
    baseline = _compute_baseline_score(breaking_changes, category)
    explanations = [
        {"label": f"Baseline: {len(breaking_changes)} known breaking changes", "delta": baseline, "kind": "baseline"},
    ]

    # --- Step 2: Workload exposure ---
    exposed_workloads = []
    exposed_ingresses = []

    if has_cluster:
        # Match workloads
        for bc in breaking_changes:
            for hint in bc.detection_hints:
                for wl in snapshot.workloads:
                    if _match_hint_against_workload(hint, wl):
                        exposed_workloads.append(ExposedWorkload(
                            workload=wl,
                            breaking_change_id=bc.id,
                            reason=hint.get("reason", ""),
                            impact=hint.get("impact", ""),
                        ))

                # Also match ingresses for ingress-controller changes
                if category == "ingress-controller":
                    for ing in snapshot.ingresses:
                        if _match_hint_against_ingress(hint, ing):
                            exposed_ingresses.append({
                                "ingress": ing.to_dict(),
                                "breaking_change_id": bc.id,
                                "reason": hint.get("reason", ""),
                                "impact": hint.get("impact", ""),
                            })

    exposure_score = _compute_exposure_score(exposed_workloads)
    if exposure_score > 0:
        explanations.append(
            {"label": f"Workload exposure: {len(exposed_workloads)} workloads matched", "delta": exposure_score, "kind": "exposure"}
        )

    # --- Step 3: Known-safe discount ---
    safe_discount = 0.0
    if has_cluster and not exposed_workloads and not exposed_ingresses:
        safe_discount = -(baseline + exposure_score) * 0.2
        explanations.append(
            {"label": "Known-safe discount: cluster present, no workloads matched", "delta": safe_discount, "kind": "discount"}
        )

    # --- Step 4: History prior ---
    relevant_fixes = _find_relevant_fixes(category, repo)
    history_score = min(len(relevant_fixes) * 3, 15.0)
    if history_score > 0:
        explanations.append(
            {"label": f"History prior: {len(relevant_fixes)} relevant team fixes", "delta": history_score, "kind": "history"}
        )

    # --- Final score ---
    score = max(0.0, min(100.0, baseline + exposure_score + safe_discount + history_score))
    severity = _severity_label(score)

    # --- Rollout risk ---
    rollout_risk = None
    if has_cluster:
        ds_count = sum(1 for w in snapshot.workloads if w.kind == "DaemonSet")
        ss_count = sum(1 for w in snapshot.workloads if w.kind == "StatefulSet")
        total_pods = sum(w.replicas for w in snapshot.workloads)
        total_nodes = sum(np.count for np in snapshot.node_pools)
        rollout_risk = RolloutRisk(
            total_node_count=total_nodes,
            affected_node_pool_count=len(snapshot.node_pools),
            total_pod_estimate=total_pods,
            daemonset_count=ds_count,
            statefulset_count=ss_count,
        ).to_dict()

    # --- Platform risks ---
    platform_risks = []
    for bc in breaking_changes:
        platform_risks.append({
            "id": bc.id,
            "title": bc.title,
            "severity": bc.severity,
            "description": bc.description,
            "consequence": bc.consequence,
            "tags": bc.tags,
        })

    # --- Cluster exposure (deduplicated by workload name + breaking change) ---
    seen_exposure = set()
    deduped_exposure = []
    for ew in exposed_workloads:
        key = (ew.workload.name, ew.workload.namespace, ew.breaking_change_id)
        if key not in seen_exposure:
            seen_exposure.add(key)
            deduped_exposure.append(ew.to_dict())

    # Add ingress exposure
    for ie in exposed_ingresses:
        ing = ie["ingress"]
        key = (ing["name"], ing["namespace"], ie["breaking_change_id"])
        if key not in seen_exposure:
            seen_exposure.add(key)
            deduped_exposure.append(ie)

    return K8sImpactResult(
        change_name=entry.display_name,
        category=category,
        from_version=from_version,
        to_version=to_version,
        score=round(score, 1),
        severity=severity,
        recommendation=_RECOMMENDATION.get(severity, _RECOMMENDATION["low"]),
        platform_risks=platform_risks,
        cluster_exposure=deduped_exposure,
        rollout_risk=rollout_risk,
        pre_checks=entry.pre_checks,
        post_checks=entry.post_checks,
        relevant_fixes=relevant_fixes,
        score_explanation=explanations,
        has_cluster_data=has_cluster,
    )
