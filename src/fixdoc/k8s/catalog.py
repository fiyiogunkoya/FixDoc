"""Curated knowledge base of Kubernetes platform change consequences."""

import sys
from pathlib import Path
from typing import Optional

import yaml

from .models import BreakingChange, CatalogEntry


# ---------------------------------------------------------------------------
# Version normalization
# ---------------------------------------------------------------------------


def _normalize_version(v: str) -> str:
    """Strip 'v' prefix and lowercase for matching."""
    return v.lstrip("vV").strip().lower()


def _major_minor(v: str) -> str:
    """Extract major.minor from a version string (e.g. '1.28.3' -> '1.28')."""
    parts = _normalize_version(v).split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


# ---------------------------------------------------------------------------
# Catalog entries — V1: 4 AKS change types
# ---------------------------------------------------------------------------

_CATALOG: list[CatalogEntry] = [
    # -----------------------------------------------------------------------
    # 1. OS Upgrade: Azure Linux 2.0 -> 3.0
    # -----------------------------------------------------------------------
    CatalogEntry(
        category="os-upgrade",
        from_version="azurelinux:2.0",
        to_version="azurelinux:3.0",
        display_name="Azure Linux 2.0 to 3.0",
        breaking_changes=[
            BreakingChange(
                id="os-azl3-glibc",
                title="glibc 2.35 to 2.38",
                severity="critical",
                description=(
                    "Azure Linux 3.0 ships glibc 2.38. Statically linked binaries "
                    "compiled against glibc 2.35 may encounter symbol version "
                    "mismatches. Containers using distroless or scratch base images "
                    "with pre-compiled binaries are most at risk."
                ),
                consequence=(
                    "Pods crash on startup with 'version GLIBC_2.36 not found' or "
                    "similar symbol resolution errors."
                ),
                detection_hints=[
                    {
                        "field": "images",
                        "pattern": r"(distroless|scratch|alpine|static)",
                        "reason": "Container uses a minimal base image that may bundle old glibc-linked binaries",
                        "impact": "Binary may fail at runtime with glibc symbol errors",
                    },
                ],
                tags=["glibc", "azurelinux", "os-upgrade", "aks"],
                references=[
                    "https://learn.microsoft.com/en-us/azure/aks/azure-linux-aks-partner-solutions",
                ],
            ),
            BreakingChange(
                id="os-azl3-cgroupv2",
                title="cgroup v2 default",
                severity="critical",
                description=(
                    "Azure Linux 3.0 defaults to cgroup v2 (unified hierarchy). "
                    "Workloads that mount /sys/fs/cgroup or use cgroup v1 paths "
                    "directly will break. Java < 15, some monitoring agents, and "
                    "custom resource controllers are commonly affected."
                ),
                consequence=(
                    "Containers mounting /sys/fs/cgroup see an empty or restructured "
                    "filesystem. Resource limits may not be read correctly, causing "
                    "OOM or CPU throttling."
                ),
                detection_hints=[
                    {
                        "field": "volumes",
                        "pattern": r"/sys/fs/cgroup",
                        "reason": "Workload mounts /sys/fs/cgroup which changes layout under cgroup v2",
                        "impact": "cgroup paths will differ; resource limit detection may break",
                    },
                    {
                        "field": "security_context",
                        "pattern": r"privileged.*true",
                        "reason": "Privileged container has direct access to host cgroup filesystem",
                        "impact": "cgroup v1 assumptions in container code will break",
                    },
                ],
                tags=["cgroup", "cgroupv2", "azurelinux", "os-upgrade", "aks"],
                references=[
                    "https://kubernetes.io/docs/concepts/architecture/cgroups/",
                ],
            ),
            BreakingChange(
                id="os-azl3-systemd",
                title="systemd 252 to 255",
                severity="high",
                description=(
                    "systemd 255 changes default unit behavior and journal format. "
                    "DaemonSets that interact with host systemd (e.g., log "
                    "collectors, node agents) may encounter changed unit states "
                    "or journal field names."
                ),
                consequence=(
                    "Node-level DaemonSets reading journald may miss logs or "
                    "fail to parse changed field formats."
                ),
                detection_hints=[
                    {
                        "field": "volumes",
                        "pattern": r"/var/log/journal|/run/systemd",
                        "reason": "Workload mounts host systemd/journal paths",
                        "impact": "Journal format changes may break log parsing",
                    },
                ],
                tags=["systemd", "azurelinux", "os-upgrade", "aks"],
            ),
            BreakingChange(
                id="os-azl3-kernel",
                title="Kernel parameter defaults changed",
                severity="medium",
                description=(
                    "Azure Linux 3.0 ships a newer kernel with different sysctl "
                    "defaults (e.g., net.core.somaxconn, vm.max_map_count). "
                    "Workloads relying on specific kernel parameter values without "
                    "explicit init containers may behave differently."
                ),
                consequence=(
                    "Performance-sensitive workloads (Elasticsearch, Redis) may "
                    "see degraded performance or startup failures if they depend "
                    "on kernel parameter values."
                ),
                detection_hints=[
                    {
                        "field": "security_context",
                        "pattern": r"capabilities|sysctl",
                        "reason": "Workload uses custom capabilities or sysctls",
                        "impact": "Kernel default changes may affect workload behavior",
                    },
                ],
                tags=["kernel", "sysctl", "azurelinux", "os-upgrade", "aks"],
            ),
        ],
        pre_checks=[
            "Audit container base images for glibc version compatibility",
            "Check for workloads mounting /sys/fs/cgroup or cgroup v1 paths",
            "Identify DaemonSets interacting with host systemd or journald",
            "Review workloads with explicit sysctl or capability requirements",
            "Test application startup in a staging node pool with Azure Linux 3.0",
        ],
        post_checks=[
            "Verify all pods reach Running state after node pool upgrade",
            "Check container logs for glibc or cgroup-related errors",
            "Validate DaemonSet log collection pipelines",
            "Confirm resource limits are correctly enforced under cgroup v2",
        ],
        risk_factors=[
            "Large number of DaemonSets increases blast radius",
            "Statically compiled Go/Rust binaries with glibc linking",
            "Java applications < version 15 with cgroup v1 assumptions",
        ],
        references=[
            "https://learn.microsoft.com/en-us/azure/aks/use-azure-linux",
        ],
        tags=["azurelinux", "os-upgrade", "aks"],
    ),

    # -----------------------------------------------------------------------
    # 2. Kubernetes Version: 1.28 -> 1.29
    # -----------------------------------------------------------------------
    CatalogEntry(
        category="k8s-version",
        from_version="1.28",
        to_version="1.29",
        display_name="Kubernetes 1.28 to 1.29",
        breaking_changes=[
            BreakingChange(
                id="k8s-129-flowcontrol",
                title="FlowControl API v1beta2 removed",
                severity="high",
                description=(
                    "The flowcontrol.apiserver.k8s.io/v1beta2 API version is "
                    "removed in 1.29. Resources must migrate to v1beta3 or v1. "
                    "Admission webhooks or controllers referencing v1beta2 will "
                    "stop working."
                ),
                consequence=(
                    "API requests to flowcontrol.apiserver.k8s.io/v1beta2 return "
                    "404. Priority-level configurations using this API version "
                    "become unmanageable."
                ),
                detection_hints=[
                    {
                        "field": "annotations",
                        "pattern": r"v1beta2|flowcontrol",
                        "reason": "Workload annotations reference deprecated FlowControl API version",
                        "impact": "FlowControl API v1beta2 is removed in 1.29",
                    },
                ],
                tags=["flowcontrol", "api-deprecation", "kubernetes", "aks"],
                references=[
                    "https://kubernetes.io/blog/2023/12/13/kubernetes-v1-29-release/",
                ],
            ),
            BreakingChange(
                id="k8s-129-kubelet-config",
                title="Kubelet configuration changes",
                severity="medium",
                description=(
                    "Several kubelet feature gates graduate to GA in 1.29 and can "
                    "no longer be disabled. KubeletCgroupDriverSystemd is locked on. "
                    "Custom kubelet configs referencing removed feature gates will "
                    "cause node startup warnings."
                ),
                consequence=(
                    "Nodes with custom kubelet configuration files may log warnings "
                    "or reject removed feature gate settings."
                ),
                detection_hints=[
                    {
                        "field": "node_selector",
                        "pattern": r"kubelet|feature-gate",
                        "reason": "Workload uses node selectors that may reference kubelet-specific labels",
                        "impact": "Kubelet configuration changes may affect node scheduling labels",
                    },
                ],
                tags=["kubelet", "feature-gate", "kubernetes", "aks"],
            ),
            BreakingChange(
                id="k8s-129-feature-gates",
                title="Feature gate promotions",
                severity="low",
                description=(
                    "Several feature gates are promoted to GA: ReadWriteOncePod, "
                    "MinDomainsInPodTopologySpread, NodeLogQuery. These are now "
                    "always enabled and cannot be toggled."
                ),
                consequence=(
                    "No immediate breakage expected, but controllers that check "
                    "feature gate state may need updates."
                ),
                detection_hints=[],
                tags=["feature-gate", "kubernetes", "aks"],
            ),
        ],
        pre_checks=[
            "Run 'kubectl get --raw /apis/flowcontrol.apiserver.k8s.io/v1beta2' to check v1beta2 usage",
            "Review admission webhooks for deprecated API version references",
            "Check custom kubelet configuration for removed feature gates",
            "Verify Helm charts reference supported API versions",
        ],
        post_checks=[
            "Verify API server is healthy: kubectl get --raw /readyz",
            "Confirm all nodes join the cluster with updated kubelet",
            "Check webhook endpoints respond correctly",
            "Validate PodDisruptionBudgets are enforced during upgrade",
        ],
        risk_factors=[
            "Custom admission webhooks using deprecated API versions",
            "Third-party operators not updated for 1.29 compatibility",
            "Custom kubelet configuration with explicit feature gates",
        ],
        references=[
            "https://kubernetes.io/blog/2023/12/13/kubernetes-v1-29-release/",
        ],
        tags=["kubernetes", "k8s-version", "aks"],
    ),

    # -----------------------------------------------------------------------
    # 3. Ingress Controller: nginx -> contour
    # -----------------------------------------------------------------------
    CatalogEntry(
        category="ingress-controller",
        from_version="nginx",
        to_version="contour",
        display_name="NGINX Ingress to Contour",
        breaking_changes=[
            BreakingChange(
                id="ingress-controller-workload",
                title="Ingress controller deployment must be replaced",
                severity="high",
                description=(
                    "The NGINX ingress controller deployment/daemonset must be "
                    "replaced with Contour. The controller handles all Ingress "
                    "routing — removing it before Contour is ready causes a "
                    "full routing outage."
                ),
                consequence=(
                    "All Ingress-based traffic stops if the old controller is "
                    "removed before the replacement is serving."
                ),
                detection_hints=[
                    {
                        "field": "images",
                        "pattern": r"ingress-nginx|nginx-ingress",
                        "applies_to": {
                            "kinds": ["Deployment", "DaemonSet"],
                        },
                        "reason": "This is the ingress controller workload being replaced",
                        "impact": "Must be replaced with Contour controller",
                    },
                    {
                        "field": "labels",
                        "pattern": r"ingress-nginx",
                        "applies_to": {
                            "kinds": ["Deployment", "DaemonSet"],
                        },
                        "reason": "Workload is labeled as part of the ingress-nginx system",
                        "impact": "This workload is part of the controller being replaced",
                    },
                ],
                tags=["ingress", "nginx", "contour", "controller", "aks"],
            ),
            BreakingChange(
                id="ingress-nginx-annotations",
                title="NGINX-specific annotations lost",
                severity="critical",
                description=(
                    "Contour does not recognize nginx.ingress.kubernetes.io/* "
                    "annotations. Rate limiting, custom headers, proxy buffer "
                    "sizes, and rewrite rules configured via NGINX annotations "
                    "will silently stop working."
                ),
                consequence=(
                    "Ingress routes lose rate limiting, custom headers, rewrites, "
                    "and proxy tuning. Traffic reaches backends without expected "
                    "middleware behavior."
                ),
                detection_hints=[
                    {
                        "field": "annotations",
                        "pattern": r"nginx\.ingress\.kubernetes\.io",
                        "reason": "Ingress uses NGINX-specific annotations that Contour ignores",
                        "impact": "NGINX annotations will be silently dropped",
                    },
                    {
                        "field": "ingress_class",
                        "pattern": r"nginx",
                        "reason": "Ingress uses NGINX ingress class that will no longer exist",
                        "impact": "Ingress becomes unmanaged after controller replacement",
                    },
                ],
                tags=["ingress", "nginx", "contour", "annotations", "aks"],
            ),
            BreakingChange(
                id="ingress-tls-passthrough",
                title="TLS passthrough configuration change",
                severity="high",
                description=(
                    "NGINX uses the nginx.ingress.kubernetes.io/ssl-passthrough "
                    "annotation. Contour requires an HTTPProxy resource with "
                    "tcpproxy.services configuration. Existing passthrough rules "
                    "won't migrate automatically."
                ),
                consequence=(
                    "TLS passthrough stops working. Backends that terminate TLS "
                    "themselves receive double-encrypted or rejected connections."
                ),
                detection_hints=[
                    {
                        "field": "annotations",
                        "pattern": r"ssl-passthrough|passthrough",
                        "reason": "Ingress uses TLS passthrough which requires Contour HTTPProxy migration",
                        "impact": "TLS passthrough will stop working without HTTPProxy configuration",
                    },
                    {
                        "field": "tls",
                        "pattern": r".",
                        "applies_to": {
                            "kinds": ["Ingress"],
                        },
                        "reason": "Ingress has TLS configuration that may need Contour-specific adjustments",
                        "impact": "TLS termination behavior may change",
                    },
                ],
                tags=["ingress", "tls", "contour", "aks"],
            ),
            BreakingChange(
                id="ingress-ratelimit",
                title="Rate-limit configuration incompatible",
                severity="medium",
                description=(
                    "NGINX rate limiting (nginx.ingress.kubernetes.io/limit-rps, "
                    "limit-connections) has no Contour annotation equivalent. "
                    "Contour uses HTTPProxy RateLimitPolicy or external rate "
                    "limiting via global config."
                ),
                consequence=(
                    "Rate limiting is silently disabled. Backends may receive "
                    "unthrottled traffic, risking overload."
                ),
                detection_hints=[
                    {
                        "field": "annotations",
                        "pattern": r"limit-rps|limit-connections|rate.limit",
                        "reason": "Ingress uses NGINX rate-limit annotations not supported by Contour",
                        "impact": "Rate limiting will be disabled until Contour RateLimitPolicy is configured",
                    },
                ],
                tags=["ingress", "rate-limit", "contour", "aks"],
            ),
        ],
        pre_checks=[
            "Inventory all Ingress resources with NGINX-specific annotations",
            "Identify Ingress resources using TLS passthrough",
            "Map rate-limit annotations to Contour RateLimitPolicy equivalents",
            "Check for custom NGINX configuration snippets (config-snippet annotation)",
            "Verify Contour CRDs (HTTPProxy) are installed in the cluster",
        ],
        post_checks=[
            "Verify all Ingress routes return expected HTTP status codes",
            "Test TLS termination and passthrough endpoints",
            "Confirm rate limiting is active via load test",
            "Check Contour/Envoy logs for routing errors",
        ],
        risk_factors=[
            "High number of Ingress resources with NGINX annotations",
            "TLS passthrough in use",
            "Custom NGINX configuration snippets",
        ],
        references=[
            "https://projectcontour.io/docs/main/config/ingress/",
        ],
        tags=["ingress", "nginx", "contour", "aks"],
    ),

    # -----------------------------------------------------------------------
    # 4. Node Pool SKU: generic VM size change
    # -----------------------------------------------------------------------
    CatalogEntry(
        category="node-pool-sku",
        from_version="Standard_D2s_v3",
        to_version="Standard_D4s_v3",
        display_name="Node Pool VM Size Change",
        breaking_changes=[
            BreakingChange(
                id="sku-memory-oom",
                title="Reduced memory/CPU may cause OOMKill",
                severity="critical",
                description=(
                    "If downsizing, the new SKU may not have enough memory or "
                    "CPU to satisfy pod resource requests. Pods will be evicted "
                    "or OOMKilled. Even upsizing can cause issues if pod anti-"
                    "affinity rules depend on node count."
                ),
                consequence=(
                    "Pods with resource requests exceeding new SKU capacity "
                    "become unschedulable or get OOMKilled."
                ),
                detection_hints=[
                    {
                        "field": "resource_requests",
                        "pattern": r".",
                        "reason": "Workload has explicit resource requests that may exceed new SKU capacity",
                        "impact": "Pods may be evicted or OOMKilled if requests exceed new SKU limits",
                    },
                    {
                        "field": "resource_limits",
                        "pattern": r".",
                        "reason": "Workload has resource limits set",
                        "impact": "Resource limits may need adjustment for new SKU capacity",
                    },
                ],
                tags=["sku", "oom", "resources", "node-pool", "aks"],
            ),
            BreakingChange(
                id="sku-ephemeral-disk",
                title="Ephemeral disk size change",
                severity="high",
                description=(
                    "Different VM SKUs have different ephemeral OS disk sizes. "
                    "Workloads using emptyDir volumes backed by the node's "
                    "ephemeral disk may lose storage capacity."
                ),
                consequence=(
                    "emptyDir volumes may hit disk pressure sooner. Pods "
                    "using large temporary storage could be evicted."
                ),
                detection_hints=[
                    {
                        "field": "volumes",
                        "pattern": r"emptyDir",
                        "reason": "Workload uses emptyDir volumes backed by node ephemeral storage",
                        "impact": "Available ephemeral storage may change with new SKU",
                    },
                ],
                tags=["sku", "disk", "ephemeral", "node-pool", "aks"],
            ),
            BreakingChange(
                id="sku-gpu",
                title="GPU availability change",
                severity="high",
                description=(
                    "GPU-enabled SKUs (NC*, ND*, NV* series) have different GPU "
                    "counts and types. Workloads with nvidia.com/gpu resource "
                    "requests or GPU tolerations may not schedule on the new SKU."
                ),
                consequence=(
                    "GPU workloads become unschedulable if the new SKU lacks "
                    "the required GPU type or count."
                ),
                detection_hints=[
                    {
                        "field": "resource_requests",
                        "pattern": r"gpu|nvidia",
                        "reason": "Workload requests GPU resources",
                        "impact": "GPU availability may differ on the new SKU",
                    },
                    {
                        "field": "tolerations",
                        "pattern": r"gpu|nvidia|sku",
                        "reason": "Workload has GPU-related tolerations",
                        "impact": "GPU tolerations may not match new SKU taints",
                    },
                ],
                tags=["sku", "gpu", "nvidia", "node-pool", "aks"],
            ),
            BreakingChange(
                id="sku-accelnet",
                title="Accelerated networking change",
                severity="medium",
                description=(
                    "Some VM SKUs support accelerated networking while others "
                    "do not. Changing SKU may enable or disable accelerated "
                    "networking, affecting network performance and potentially "
                    "network plugin behavior."
                ),
                consequence=(
                    "Network latency characteristics change. Workloads sensitive "
                    "to network performance may see degraded or improved behavior."
                ),
                detection_hints=[],
                tags=["sku", "networking", "accelerated-networking", "node-pool", "aks"],
            ),
        ],
        pre_checks=[
            "Compare CPU/memory of old vs new SKU",
            "Review pod resource requests against new SKU capacity",
            "Check for emptyDir volumes with large sizeLimit",
            "Identify GPU workloads if changing to/from GPU SKU",
            "Verify accelerated networking support on new SKU",
        ],
        post_checks=[
            "Verify all pods reschedule on new node pool",
            "Check for OOMKilled or Evicted pods",
            "Validate emptyDir storage is adequate",
            "Confirm GPU workloads are running if applicable",
        ],
        risk_factors=[
            "Downsizing VM SKU with memory-intensive workloads",
            "GPU workloads on the affected node pool",
            "StatefulSets that cannot tolerate node replacement",
        ],
        references=[
            "https://learn.microsoft.com/en-us/azure/aks/manage-node-pools",
        ],
        tags=["sku", "node-pool", "vm-size", "aks"],
    ),
]


# ---------------------------------------------------------------------------
# YAML custom catalog loading
# ---------------------------------------------------------------------------


def _load_yaml_file(path: Path) -> list:
    """Parse a single YAML file into CatalogEntry objects.

    Handles two formats:
    - Single entry: top-level dict with 'category' key
    - Multi-entry: top-level dict with 'entries' key (list)

    Returns [] on invalid YAML or missing required fields.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        print(f"Warning: could not load {path}: {exc}", file=sys.stderr)
        return []

    if not isinstance(data, dict):
        return []

    entries_data = []
    if "entries" in data:
        raw = data["entries"]
        if isinstance(raw, list):
            entries_data = raw
    elif "category" in data:
        entries_data = [data]
    else:
        return []

    results = []
    for entry_dict in entries_data:
        if not isinstance(entry_dict, dict):
            continue
        if not all(k in entry_dict for k in ("category", "from_version", "to_version")):
            continue
        try:
            entry = CatalogEntry.from_dict(entry_dict)
            entry.source = path.name
            results.append(entry)
        except (KeyError, TypeError):
            continue

    return results


def load_custom_entries(catalog_dir: Optional[Path] = None) -> list:
    """Load custom catalog entries from .fixdoc-catalog/ at git root.

    Args:
        catalog_dir: Explicit path. If None, auto-discovers via git root.

    Returns list of CatalogEntry objects with source set to filename.
    """
    if catalog_dir is None:
        from ..pending import _find_git_root
        git_root = _find_git_root()
        catalog_dir = git_root / ".fixdoc-catalog"

    if not catalog_dir.is_dir():
        return []

    entries = []
    for p in sorted(catalog_dir.iterdir()):
        if p.suffix.lower() in (".yaml", ".yml"):
            entries.extend(_load_yaml_file(p))
    return entries


def _catalog_key(entry: CatalogEntry) -> tuple:
    """Override key for merging: (category, normalized_from, normalized_to)."""
    return (
        entry.category.lower().strip(),
        _normalize_version(entry.from_version),
        _normalize_version(entry.to_version),
    )


def build_merged_catalog(custom_entries: list) -> list:
    """Merge built-in catalog with custom entries.

    Custom entries with the same (category, from_version, to_version) key
    override built-in entries.
    """
    if not custom_entries:
        return list(_CATALOG)

    custom_keys = {_catalog_key(e) for e in custom_entries}
    merged = [e for e in _CATALOG if _catalog_key(e) not in custom_keys]
    merged.extend(custom_entries)
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_change(
    category: str, from_v: str, to_v: str, catalog: Optional[list] = None
) -> Optional[CatalogEntry]:
    """Look up a catalog entry by category and version range.

    Version matching is relaxed: strips 'v' prefix and compares major.minor
    for k8s-version, exact lowercased match for others.
    """
    source = catalog if catalog is not None else _CATALOG
    cat_lower = category.lower().strip()
    from_norm = _normalize_version(from_v)
    to_norm = _normalize_version(to_v)

    for entry in source:
        if entry.category != cat_lower:
            continue

        entry_from = _normalize_version(entry.from_version)
        entry_to = _normalize_version(entry.to_version)

        if cat_lower == "k8s-version":
            if _major_minor(from_v) == _major_minor(entry.from_version) and \
               _major_minor(to_v) == _major_minor(entry.to_version):
                return entry
        elif cat_lower == "node-pool-sku":
            # Generic SKU entry — match any SKU change in same category
            return entry
        else:
            if from_norm == entry_from and to_norm == entry_to:
                return entry

    return None


def list_categories(catalog: Optional[list] = None) -> list:
    """Return available change categories."""
    source = catalog if catalog is not None else _CATALOG
    seen = []
    for entry in source:
        if entry.category not in seen:
            seen.append(entry.category)
    return seen


def list_changes(category: Optional[str] = None, catalog: Optional[list] = None) -> list:
    """Return catalog entries, optionally filtered by category."""
    source = catalog if catalog is not None else _CATALOG
    if category is None:
        return list(source)
    cat_lower = category.lower().strip()
    return [e for e in source if e.category == cat_lower]
