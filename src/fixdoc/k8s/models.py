"""Data models for Kubernetes change intelligence."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Knowledge Base Models
# ---------------------------------------------------------------------------


@dataclass
class BreakingChange:
    """A single known breaking change within a platform transition."""

    id: str
    title: str
    severity: str  # critical | high | medium | low
    description: str
    consequence: str
    detection_hints: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    references: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "description": self.description,
            "consequence": self.consequence,
            "detection_hints": self.detection_hints,
            "tags": self.tags,
            "references": self.references,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BreakingChange":
        return cls(
            id=data["id"],
            title=data["title"],
            severity=data.get("severity", "medium"),
            description=data.get("description", ""),
            consequence=data.get("consequence", ""),
            detection_hints=data.get("detection_hints", []),
            tags=data.get("tags", []),
            references=data.get("references", []),
        )


@dataclass
class CatalogEntry:
    """A curated platform change with its known consequences."""

    category: str  # os-upgrade | k8s-version | ingress-controller | node-pool-sku
    from_version: str
    to_version: str
    display_name: str
    breaking_changes: list = field(default_factory=list)  # list[BreakingChange]
    pre_checks: list = field(default_factory=list)
    post_checks: list = field(default_factory=list)
    risk_factors: list = field(default_factory=list)
    references: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    source: str = "built-in"  # "built-in" or filename for custom entries

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "display_name": self.display_name,
            "breaking_changes": [
                bc.to_dict() if isinstance(bc, BreakingChange) else bc
                for bc in self.breaking_changes
            ],
            "pre_checks": self.pre_checks,
            "post_checks": self.post_checks,
            "risk_factors": self.risk_factors,
            "references": self.references,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CatalogEntry":
        return cls(
            category=data["category"],
            from_version=data["from_version"],
            to_version=data["to_version"],
            display_name=data.get("display_name", ""),
            breaking_changes=[
                BreakingChange.from_dict(bc) for bc in data.get("breaking_changes", [])
            ],
            pre_checks=data.get("pre_checks", []),
            post_checks=data.get("post_checks", []),
            risk_factors=data.get("risk_factors", []),
            references=data.get("references", []),
            tags=data.get("tags", []),
            source=data.get("source", "built-in"),
        )


# ---------------------------------------------------------------------------
# Cluster State Models
# ---------------------------------------------------------------------------


@dataclass
class NodePool:
    """A node pool in the cluster."""

    name: str
    os: Optional[str] = None
    k8s_version: Optional[str] = None
    sku: Optional[str] = None
    labels: dict = field(default_factory=dict)
    taints: list = field(default_factory=list)
    count: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "os": self.os,
            "k8s_version": self.k8s_version,
            "sku": self.sku,
            "labels": self.labels,
            "taints": self.taints,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NodePool":
        return cls(
            name=data["name"],
            os=data.get("os"),
            k8s_version=data.get("k8s_version"),
            sku=data.get("sku"),
            labels=data.get("labels", {}),
            taints=data.get("taints", []),
            count=data.get("count", 0),
        )


@dataclass
class Workload:
    """A workload (Deployment, DaemonSet, StatefulSet, Job) in the cluster."""

    kind: str
    name: str
    namespace: str
    replicas: int = 1
    images: list = field(default_factory=list)
    volumes: list = field(default_factory=list)
    security_context: Optional[dict] = None
    node_selector: Optional[dict] = None
    tolerations: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)
    annotations: dict = field(default_factory=dict)
    resource_requests: Optional[dict] = None
    resource_limits: Optional[dict] = None
    spec_raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "namespace": self.namespace,
            "replicas": self.replicas,
            "images": self.images,
            "volumes": self.volumes,
            "security_context": self.security_context,
            "node_selector": self.node_selector,
            "tolerations": self.tolerations,
            "labels": self.labels,
            "annotations": self.annotations,
            "resource_requests": self.resource_requests,
            "resource_limits": self.resource_limits,
            "spec_raw": self.spec_raw,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Workload":
        return cls(
            kind=data.get("kind", "Deployment"),
            name=data["name"],
            namespace=data.get("namespace", "default"),
            replicas=data.get("replicas", 1),
            images=data.get("images", []),
            volumes=data.get("volumes", []),
            security_context=data.get("security_context"),
            node_selector=data.get("node_selector"),
            tolerations=data.get("tolerations", []),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            resource_requests=data.get("resource_requests"),
            resource_limits=data.get("resource_limits"),
            spec_raw=data.get("spec_raw", {}),
        )


@dataclass
class IngressResource:
    """An Ingress resource in the cluster."""

    name: str
    namespace: str
    ingress_class: Optional[str] = None
    rules: list = field(default_factory=list)
    tls: list = field(default_factory=list)
    annotations: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "ingress_class": self.ingress_class,
            "rules": self.rules,
            "tls": self.tls,
            "annotations": self.annotations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IngressResource":
        return cls(
            name=data["name"],
            namespace=data.get("namespace", "default"),
            ingress_class=data.get("ingress_class"),
            rules=data.get("rules", []),
            tls=data.get("tls", []),
            annotations=data.get("annotations", {}),
        )


@dataclass
class ClusterSnapshot:
    """A point-in-time snapshot of cluster state."""

    node_pools: list = field(default_factory=list)  # list[NodePool]
    workloads: list = field(default_factory=list)  # list[Workload]
    ingresses: list = field(default_factory=list)  # list[IngressResource]
    services: list = field(default_factory=list)
    network_policies: list = field(default_factory=list)
    crds: list = field(default_factory=list)
    helm_releases: list = field(default_factory=list)
    namespaces: list = field(default_factory=list)
    snapshot_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "node_pools": [
                np.to_dict() if isinstance(np, NodePool) else np
                for np in self.node_pools
            ],
            "workloads": [
                w.to_dict() if isinstance(w, Workload) else w
                for w in self.workloads
            ],
            "ingresses": [
                i.to_dict() if isinstance(i, IngressResource) else i
                for i in self.ingresses
            ],
            "services": self.services,
            "network_policies": self.network_policies,
            "crds": self.crds,
            "helm_releases": self.helm_releases,
            "namespaces": self.namespaces,
            "snapshot_at": self.snapshot_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClusterSnapshot":
        return cls(
            node_pools=[
                NodePool.from_dict(np) for np in data.get("node_pools", [])
            ],
            workloads=[
                Workload.from_dict(w) for w in data.get("workloads", [])
            ],
            ingresses=[
                IngressResource.from_dict(i) for i in data.get("ingresses", [])
            ],
            services=data.get("services", []),
            network_policies=data.get("network_policies", []),
            crds=data.get("crds", []),
            helm_releases=data.get("helm_releases", []),
            namespaces=data.get("namespaces", []),
            snapshot_at=data.get("snapshot_at", _now_iso()),
        )


# ---------------------------------------------------------------------------
# Result Models
# ---------------------------------------------------------------------------


@dataclass
class ExposedWorkload:
    """A workload flagged by a breaking change detection hint."""

    workload: Workload
    breaking_change_id: str
    reason: str
    impact: str

    def to_dict(self) -> dict:
        return {
            "workload": self.workload.to_dict() if isinstance(self.workload, Workload) else self.workload,
            "breaking_change_id": self.breaking_change_id,
            "reason": self.reason,
            "impact": self.impact,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExposedWorkload":
        return cls(
            workload=Workload.from_dict(data["workload"]),
            breaking_change_id=data["breaking_change_id"],
            reason=data.get("reason", ""),
            impact=data.get("impact", ""),
        )


@dataclass
class RolloutRisk:
    """Rollout disruption estimate based on cluster state."""

    total_node_count: int = 0
    affected_node_pool_count: int = 0
    total_pod_estimate: int = 0
    daemonset_count: int = 0
    statefulset_count: int = 0
    pdb_conflicts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_node_count": self.total_node_count,
            "affected_node_pool_count": self.affected_node_pool_count,
            "total_pod_estimate": self.total_pod_estimate,
            "daemonset_count": self.daemonset_count,
            "statefulset_count": self.statefulset_count,
            "pdb_conflicts": self.pdb_conflicts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RolloutRisk":
        return cls(
            total_node_count=data.get("total_node_count", 0),
            affected_node_pool_count=data.get("affected_node_pool_count", 0),
            total_pod_estimate=data.get("total_pod_estimate", 0),
            daemonset_count=data.get("daemonset_count", 0),
            statefulset_count=data.get("statefulset_count", 0),
            pdb_conflicts=data.get("pdb_conflicts", []),
        )


@dataclass
class K8sImpactResult:
    """Complete result of a Kubernetes change impact analysis."""

    analysis_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = field(default_factory=_now_iso)
    change_name: str = ""
    category: str = ""
    from_version: str = ""
    to_version: str = ""
    score: float = 0.0
    severity: str = "low"
    recommendation: str = ""
    platform_risks: list = field(default_factory=list)
    cluster_exposure: list = field(default_factory=list)
    rollout_risk: Optional[dict] = None
    pre_checks: list = field(default_factory=list)
    post_checks: list = field(default_factory=list)
    relevant_fixes: list = field(default_factory=list)
    score_explanation: list = field(default_factory=list)
    has_cluster_data: bool = False

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "timestamp": self.timestamp,
            "change_name": self.change_name,
            "category": self.category,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "score": self.score,
            "severity": self.severity,
            "recommendation": self.recommendation,
            "platform_risks": self.platform_risks,
            "cluster_exposure": self.cluster_exposure,
            "rollout_risk": self.rollout_risk,
            "pre_checks": self.pre_checks,
            "post_checks": self.post_checks,
            "relevant_fixes": self.relevant_fixes,
            "score_explanation": self.score_explanation,
            "has_cluster_data": self.has_cluster_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "K8sImpactResult":
        return cls(
            analysis_id=data.get("analysis_id", uuid.uuid4().hex[:8]),
            timestamp=data.get("timestamp", _now_iso()),
            change_name=data.get("change_name", ""),
            category=data.get("category", ""),
            from_version=data.get("from_version", ""),
            to_version=data.get("to_version", ""),
            score=data.get("score", 0.0),
            severity=data.get("severity", "low"),
            recommendation=data.get("recommendation", ""),
            platform_risks=data.get("platform_risks", []),
            cluster_exposure=data.get("cluster_exposure", []),
            rollout_risk=data.get("rollout_risk"),
            pre_checks=data.get("pre_checks", []),
            post_checks=data.get("post_checks", []),
            relevant_fixes=data.get("relevant_fixes", []),
            score_explanation=data.get("score_explanation", []),
            has_cluster_data=data.get("has_cluster_data", False),
        )
