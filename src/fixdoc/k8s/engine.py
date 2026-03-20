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

# Deprecated — kept for backward compat. Use _K8S_TAG_TIERS instead.
_K8S_SEARCH_TAGS = {
    "os-upgrade": ["azurelinux", "os-upgrade", "cgroup", "glibc", "aks", "kubernetes"],
    "k8s-version": ["kubernetes", "k8s", "api-deprecation", "kubelet", "aks"],
    "ingress-controller": ["ingress", "nginx", "contour", "envoy", "aks", "kubernetes"],
    "node-pool-sku": ["node-pool", "sku", "oom", "gpu", "aks", "kubernetes"],
}

# Tiered tag system: fix must match at least 1 required tag.
_K8S_TAG_TIERS = {
    "os-upgrade": {
        "required": ["os-upgrade", "azurelinux", "cgroup", "cgroupv2", "glibc", "systemd", "kernel"],
        "boost": ["aks", "kubernetes"],
    },
    "k8s-version": {
        "required": ["api-deprecation", "flowcontrol", "kubelet", "feature-gate", "k8s-version"],
        "boost": ["kubernetes", "k8s", "aks"],
    },
    "ingress-controller": {
        "required": ["ingress", "nginx", "contour", "envoy", "gateway-api", "httproute", "tls", "ssl"],
        "boost": ["aks", "kubernetes"],
    },
    "node-pool-sku": {
        "required": ["node-pool", "sku", "oom", "gpu", "vm-size"],
        "boost": ["aks", "kubernetes"],
    },
}

_CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.5, "low": 0.25}


# ---------------------------------------------------------------------------
# Match confidence classification
# ---------------------------------------------------------------------------


def _classify_match_confidence(hint: dict) -> str:
    """Classify match confidence based on hint pattern specificity."""
    pattern = hint.get("pattern", "")
    has_scope = bool(hint.get("applies_to"))

    # Trivial patterns
    if pattern in (".", ".*", ".+", ".?") or len(pattern) <= 2:
        return "medium" if has_scope else "low"

    # Broad OR patterns with only short tokens
    tokens = [t.strip() for t in pattern.replace("(", "").replace(")", "").split("|")]
    if all(len(t) <= 5 for t in tokens) and len(tokens) <= 3:
        return "medium" if has_scope else "low"

    return "high"


# ---------------------------------------------------------------------------
# applies_to scope matching
# ---------------------------------------------------------------------------


def _matches_applies_to(applies_to: dict, entity, is_ingress: bool) -> bool:
    """Check if an entity matches the applies_to scope.

    All sub-fields use AND logic. Multiple values within a sub-field use OR logic.
    If applies_to is empty or None -> match all (backward compat).
    """
    if not applies_to:
        return True

    # Kind check
    kinds = applies_to.get("kinds")
    if kinds:
        entity_kind = "Ingress" if is_ingress else getattr(entity, "kind", "")
        if entity_kind not in kinds:
            return False

    # Namespace check (regex)
    namespaces = applies_to.get("namespaces")
    if namespaces:
        entity_ns = getattr(entity, "namespace", "")
        if not any(re.search(ns_pat, entity_ns, re.IGNORECASE) for ns_pat in namespaces):
            return False

    # Name check (regex)
    names = applies_to.get("names")
    if names:
        entity_name = getattr(entity, "name", "")
        if not any(re.search(name_pat, entity_name, re.IGNORECASE) for name_pat in names):
            return False

    # Image check (regex) — only for workloads
    images = applies_to.get("images")
    if images and not is_ingress:
        entity_images = getattr(entity, "images", []) or []
        matched = False
        for img_pat in images:
            for img in entity_images:
                if re.search(img_pat, img, re.IGNORECASE):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            return False

    # Label check (regex on values)
    # Supports dict {"key": "pattern"} or list ["key=pattern", ...]
    labels = applies_to.get("labels")
    if labels:
        entity_labels = getattr(entity, "labels", {}) or {}
        if isinstance(labels, list):
            # Convert list of "key=value" strings to dict
            label_dict = {}
            for item in labels:
                if "=" in str(item):
                    k, v = str(item).split("=", 1)
                    label_dict[k] = v
                else:
                    # Bare key — match any value
                    label_dict[str(item)] = ".*"
            labels = label_dict
        for key, val_pattern in labels.items():
            entity_val = entity_labels.get(key)
            if entity_val is None:
                return False
            if not re.search(val_pattern, str(entity_val), re.IGNORECASE):
                return False

    return True


# ---------------------------------------------------------------------------
# Workload matching
# ---------------------------------------------------------------------------


def _match_hint_against_workload(hint: dict, workload: Workload) -> bool:
    """Check if a detection hint matches a workload."""
    # Check applies_to scope first
    applies_to = hint.get("applies_to")
    if applies_to and not _matches_applies_to(applies_to, workload, is_ingress=False):
        return False

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
    # Check applies_to scope first
    applies_to = hint.get("applies_to")
    if applies_to and not _matches_applies_to(applies_to, ingress, is_ingress=True):
        return False

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
        "ingress_class": ingress.ingress_class,
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
    """Query fix database for team knowledge relevant to this change type.

    Uses tiered tag scoring: fix must match at least 1 required tag.
    Required tags score 10 pts each, boost tags score 2 pts each.
    """
    if repo is None:
        return []

    tiers = _K8S_TAG_TIERS.get(category)
    if tiers is None:
        return []

    required = set(tiers["required"])
    boost = set(tiers["boost"])

    all_fixes = repo.list_all()
    scored = []

    for fix in all_fixes:
        fix_tags = set()
        if isinstance(fix.tags, str):
            fix_tags = {t.strip().lower() for t in fix.tags.split(",") if t.strip()}
        elif isinstance(fix.tags, list):
            fix_tags = {t.strip().lower() for t in fix.tags if isinstance(t, str)}

        required_matches = fix_tags & required
        if not required_matches:
            continue

        score = len(required_matches) * 10 + len(fix_tags & boost) * 2
        scored.append((score, {
            "id": fix.id[:8],
            "issue": fix.issue,
            "resolution": fix.resolution,
            "tags": fix.tags,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:10]]


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

    # --- Step 2: Workload exposure (with dedup + confidence) ---
    raw_wl_matches = []  # (workload, bc_id, reason, impact, confidence)
    raw_ing_matches = []  # (ingress, bc_id, reason, impact, confidence)

    if has_cluster:
        for bc in breaking_changes:
            for hint in bc.detection_hints:
                confidence = _classify_match_confidence(hint)
                for wl in snapshot.workloads:
                    if _match_hint_against_workload(hint, wl):
                        raw_wl_matches.append((wl, bc.id, hint.get("reason", ""), hint.get("impact", ""), confidence))

                if category == "ingress-controller":
                    for ing in snapshot.ingresses:
                        if _match_hint_against_ingress(hint, ing):
                            raw_ing_matches.append((ing, bc.id, hint.get("reason", ""), hint.get("impact", ""), confidence))

    # Aggregate by workload identity — each unique workload counted once
    wl_map = {}  # (name, ns) -> {workload, matches, best_confidence}
    for wl, bc_id, reason, impact, conf in raw_wl_matches:
        key = (wl.name, wl.namespace)
        if key not in wl_map:
            wl_map[key] = {"workload": wl, "matches": [], "best_confidence": conf}
        # Dedup per (workload, bc_id)
        existing_bcs = {m["bc_id"] for m in wl_map[key]["matches"]}
        if bc_id not in existing_bcs:
            wl_map[key]["matches"].append({"bc_id": bc_id, "reason": reason, "impact": impact, "confidence": conf})
        # Track best confidence
        if _CONFIDENCE_WEIGHT.get(conf, 0) > _CONFIDENCE_WEIGHT.get(wl_map[key]["best_confidence"], 0):
            wl_map[key]["best_confidence"] = conf

    ing_map = {}  # (name, ns) -> {ingress, matches, best_confidence}
    for ing, bc_id, reason, impact, conf in raw_ing_matches:
        key = (ing.name, ing.namespace)
        if key not in ing_map:
            ing_map[key] = {"ingress": ing, "matches": [], "best_confidence": conf}
        existing_bcs = {m["bc_id"] for m in ing_map[key]["matches"]}
        if bc_id not in existing_bcs:
            ing_map[key]["matches"].append({"bc_id": bc_id, "reason": reason, "impact": impact, "confidence": conf})
        if _CONFIDENCE_WEIGHT.get(conf, 0) > _CONFIDENCE_WEIGHT.get(ing_map[key]["best_confidence"], 0):
            ing_map[key]["best_confidence"] = conf

    # Compute exposure score from unique entities, weighted by confidence
    kind_weights = {"DaemonSet": 5, "StatefulSet": 4, "Deployment": 2, "Job": 1}
    exposure_total = 0.0
    for agg in wl_map.values():
        kind = agg["workload"].kind
        conf_weight = _CONFIDENCE_WEIGHT.get(agg["best_confidence"], 1.0)
        exposure_total += kind_weights.get(kind, 1) * conf_weight
    for agg in ing_map.values():
        exposure_total += 2.0 * _CONFIDENCE_WEIGHT.get(agg["best_confidence"], 1.0)
    exposure_score = min(exposure_total, 30.0)

    unique_count = len(wl_map) + len(ing_map)
    if exposure_score > 0:
        explanations.append(
            {"label": f"Workload exposure: {unique_count} unique workloads matched", "delta": exposure_score, "kind": "exposure"}
        )

    # --- Step 3: Known-safe discount ---
    safe_discount = 0.0
    if has_cluster and not wl_map and not ing_map:
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

    # --- Rollout risk (category-specific) ---
    rollout_risk = None
    if has_cluster:
        if category == "ingress-controller":
            rollout_risk = {
                "type": "routing",
                "ingress_count": len(snapshot.ingresses),
                "affected_namespaces": len({ing.namespace for ing in snapshot.ingresses}),
                "has_tls": any(ing.tls for ing in snapshot.ingresses),
                "total_pod_estimate": sum(w.replicas for w in snapshot.workloads),
            }
        else:
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

    # --- Build cluster exposure output (aggregated) ---
    deduped_exposure = []
    for agg in wl_map.values():
        matches = agg["matches"]
        first = matches[0]
        entry_dict = ExposedWorkload(
            workload=agg["workload"],
            breaking_change_id=first["bc_id"],
            reason=first["reason"],
            impact=first["impact"],
        ).to_dict()
        entry_dict["match_count"] = len(matches)
        entry_dict["confidence"] = agg["best_confidence"]
        if len(matches) > 1:
            entry_dict["all_matches"] = matches
        deduped_exposure.append(entry_dict)

    for agg in ing_map.values():
        matches = agg["matches"]
        first = matches[0]
        entry_dict = {
            "ingress": agg["ingress"].to_dict(),
            "breaking_change_id": first["bc_id"],
            "reason": first["reason"],
            "impact": first["impact"],
            "match_count": len(matches),
            "confidence": agg["best_confidence"],
        }
        if len(matches) > 1:
            entry_dict["all_matches"] = matches
        deduped_exposure.append(entry_dict)

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
