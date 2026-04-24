"""Tests for Kubernetes change intelligence data models and catalog."""

import json
from pathlib import Path

import pytest

from fixdoc.k8s.models import (
    BreakingChange,
    CatalogEntry,
    ClusterSnapshot,
    ExposedWorkload,
    IngressResource,
    K8sImpactResult,
    NodePool,
    RolloutRisk,
    Workload,
)
from fixdoc.k8s.catalog import (
    list_categories,
    list_changes,
    resolve_change,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "k8s"


# ---------------------------------------------------------------------------
# BreakingChange
# ---------------------------------------------------------------------------


class TestBreakingChange:
    def test_to_dict_from_dict_roundtrip(self):
        bc = BreakingChange(
            id="test-bc",
            title="Test breaking change",
            severity="high",
            description="A test",
            consequence="Things break",
            detection_hints=[{"field": "images", "pattern": "alpine"}],
            tags=["test"],
            references=["https://example.com"],
        )
        d = bc.to_dict()
        restored = BreakingChange.from_dict(d)
        assert restored.id == bc.id
        assert restored.severity == bc.severity
        assert restored.detection_hints == bc.detection_hints

    def test_from_dict_defaults(self):
        bc = BreakingChange.from_dict({"id": "x", "title": "y"})
        assert bc.severity == "medium"
        assert bc.description == ""
        assert bc.tags == []


# ---------------------------------------------------------------------------
# CatalogEntry
# ---------------------------------------------------------------------------


class TestCatalogEntry:
    def test_to_dict_from_dict_roundtrip(self):
        entry = CatalogEntry(
            category="os-upgrade",
            from_version="azurelinux:2.0",
            to_version="azurelinux:3.0",
            display_name="Test",
            breaking_changes=[
                BreakingChange(id="bc1", title="BC1", severity="high",
                               description="", consequence=""),
            ],
            pre_checks=["Check A"],
            post_checks=["Check B"],
            tags=["aks"],
        )
        d = entry.to_dict()
        restored = CatalogEntry.from_dict(d)
        assert restored.category == "os-upgrade"
        assert len(restored.breaking_changes) == 1
        assert restored.breaking_changes[0].id == "bc1"
        assert restored.pre_checks == ["Check A"]

    def test_from_dict_defaults(self):
        entry = CatalogEntry.from_dict({
            "category": "k8s-version",
            "from_version": "1.28",
            "to_version": "1.29",
        })
        assert entry.display_name == ""
        assert entry.breaking_changes == []


# ---------------------------------------------------------------------------
# NodePool
# ---------------------------------------------------------------------------


class TestNodePool:
    def test_roundtrip(self):
        np = NodePool(
            name="system", os="Azure Linux 2.0", k8s_version="1.28.5",
            sku="Standard_D4s_v3", count=3,
        )
        d = np.to_dict()
        restored = NodePool.from_dict(d)
        assert restored.name == "system"
        assert restored.count == 3

    def test_defaults(self):
        np = NodePool.from_dict({"name": "default"})
        assert np.os is None
        assert np.count == 0
        assert np.labels == {}


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------


class TestWorkload:
    def test_roundtrip(self):
        wl = Workload(
            kind="Deployment", name="api", namespace="prod",
            replicas=3, images=["nginx:latest"],
            resource_requests={"cpu": "500m"},
        )
        d = wl.to_dict()
        restored = Workload.from_dict(d)
        assert restored.kind == "Deployment"
        assert restored.images == ["nginx:latest"]
        assert restored.resource_requests == {"cpu": "500m"}

    def test_defaults(self):
        wl = Workload.from_dict({"name": "x"})
        assert wl.kind == "Deployment"
        assert wl.namespace == "default"
        assert wl.replicas == 1
        assert wl.spec_raw == {}


# ---------------------------------------------------------------------------
# IngressResource
# ---------------------------------------------------------------------------


class TestIngressResource:
    def test_roundtrip(self):
        ing = IngressResource(
            name="api", namespace="prod", ingress_class="nginx",
            annotations={"nginx.ingress.kubernetes.io/rate-limit": "100"},
        )
        d = ing.to_dict()
        restored = IngressResource.from_dict(d)
        assert restored.ingress_class == "nginx"
        assert "rate-limit" in str(restored.annotations)

    def test_defaults(self):
        ing = IngressResource.from_dict({"name": "test"})
        assert ing.namespace == "default"
        assert ing.ingress_class is None


# ---------------------------------------------------------------------------
# ClusterSnapshot
# ---------------------------------------------------------------------------


class TestClusterSnapshot:
    def test_roundtrip(self):
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=2)],
            workloads=[Workload(kind="Deployment", name="app", namespace="default")],
            ingresses=[IngressResource(name="ing", namespace="default")],
            namespaces=["default", "kube-system"],
        )
        d = snapshot.to_dict()
        restored = ClusterSnapshot.from_dict(d)
        assert len(restored.node_pools) == 1
        assert restored.node_pools[0].name == "sys"
        assert len(restored.workloads) == 1
        assert len(restored.ingresses) == 1
        assert "kube-system" in restored.namespaces

    def test_load_fixture(self):
        with open(FIXTURE_DIR / "sample_snapshot.json") as f:
            data = json.load(f)
        snapshot = ClusterSnapshot.from_dict(data)
        assert len(snapshot.node_pools) == 2
        assert len(snapshot.workloads) == 6
        assert len(snapshot.ingresses) == 2
        assert "production" in snapshot.namespaces

    def test_empty_snapshot(self):
        snapshot = ClusterSnapshot.from_dict({})
        assert snapshot.node_pools == []
        assert snapshot.workloads == []
        assert snapshot.namespaces == []


# ---------------------------------------------------------------------------
# ExposedWorkload
# ---------------------------------------------------------------------------


class TestExposedWorkload:
    def test_roundtrip(self):
        wl = Workload(kind="DaemonSet", name="agent", namespace="monitoring")
        ew = ExposedWorkload(
            workload=wl, breaking_change_id="os-azl3-cgroupv2",
            reason="Mounts cgroup", impact="cgroup v1 paths break",
        )
        d = ew.to_dict()
        restored = ExposedWorkload.from_dict(d)
        assert restored.breaking_change_id == "os-azl3-cgroupv2"
        assert restored.workload.kind == "DaemonSet"


# ---------------------------------------------------------------------------
# RolloutRisk
# ---------------------------------------------------------------------------


class TestRolloutRisk:
    def test_roundtrip(self):
        rr = RolloutRisk(
            total_node_count=8, affected_node_pool_count=2,
            total_pod_estimate=50, daemonset_count=3, statefulset_count=1,
        )
        d = rr.to_dict()
        restored = RolloutRisk.from_dict(d)
        assert restored.total_node_count == 8
        assert restored.daemonset_count == 3

    def test_defaults(self):
        rr = RolloutRisk.from_dict({})
        assert rr.total_node_count == 0
        assert rr.pdb_conflicts == []


# ---------------------------------------------------------------------------
# K8sImpactResult
# ---------------------------------------------------------------------------


class TestK8sImpactResult:
    def test_roundtrip(self):
        result = K8sImpactResult(
            change_name="Test", category="os-upgrade",
            from_version="2.0", to_version="3.0",
            score=65.0, severity="high",
            recommendation="Stage first",
            platform_risks=[{"id": "bc1", "title": "glibc", "severity": "critical"}],
            pre_checks=["Check A"],
            has_cluster_data=True,
        )
        d = result.to_dict()
        restored = K8sImpactResult.from_dict(d)
        assert restored.score == 65.0
        assert restored.severity == "high"
        assert restored.has_cluster_data is True
        assert len(restored.platform_risks) == 1

    def test_defaults(self):
        result = K8sImpactResult.from_dict({})
        assert result.score == 0.0
        assert result.severity == "low"
        assert result.has_cluster_data is False


# ---------------------------------------------------------------------------
# Catalog API
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_list_categories(self):
        cats = list_categories()
        assert "os-upgrade" in cats
        assert "k8s-version" in cats
        assert "ingress-controller" in cats
        assert "node-pool-sku" in cats

    def test_list_changes_all(self):
        entries = list_changes()
        assert len(entries) == 4

    def test_list_changes_filtered(self):
        entries = list_changes("os-upgrade")
        assert len(entries) == 1
        assert entries[0].category == "os-upgrade"

    def test_list_changes_empty(self):
        entries = list_changes("nonexistent")
        assert entries == []

    def test_resolve_os_upgrade(self):
        entry = resolve_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0")
        assert entry is not None
        assert entry.display_name == "Azure Linux 2.0 to 3.0"
        assert len(entry.breaking_changes) == 4

    def test_resolve_k8s_version(self):
        entry = resolve_change("k8s-version", "1.28", "1.29")
        assert entry is not None
        assert "1.28" in entry.display_name or "1.29" in entry.display_name

    def test_resolve_k8s_version_with_v_prefix(self):
        entry = resolve_change("k8s-version", "v1.28.5", "v1.29.0")
        assert entry is not None

    def test_resolve_ingress_controller(self):
        entry = resolve_change("ingress-controller", "nginx", "contour")
        assert entry is not None
        assert len(entry.breaking_changes) == 4

    def test_resolve_node_pool_sku(self):
        entry = resolve_change("node-pool-sku", "Standard_D2s_v3", "Standard_D4s_v3")
        assert entry is not None

    def test_resolve_node_pool_sku_any_values(self):
        entry = resolve_change("node-pool-sku", "Standard_E4s_v5", "Standard_E8s_v5")
        assert entry is not None  # generic match

    def test_resolve_unknown_returns_none(self):
        entry = resolve_change("os-upgrade", "ubuntu:20.04", "ubuntu:22.04")
        assert entry is None

    def test_resolve_unknown_category_returns_none(self):
        entry = resolve_change("storage-upgrade", "1.0", "2.0")
        assert entry is None

    def test_breaking_changes_have_detection_hints(self):
        entry = resolve_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0")
        assert entry is not None
        hints_count = sum(len(bc.detection_hints) for bc in entry.breaking_changes)
        assert hints_count > 0

    def test_all_entries_have_pre_checks(self):
        for entry in list_changes():
            assert len(entry.pre_checks) > 0, f"{entry.category} missing pre_checks"

    def test_all_entries_have_post_checks(self):
        for entry in list_changes():
            assert len(entry.post_checks) > 0, f"{entry.category} missing post_checks"

    def test_severity_values_are_valid(self):
        valid = {"critical", "high", "medium", "low"}
        for entry in list_changes():
            for bc in entry.breaking_changes:
                assert bc.severity in valid, f"{bc.id} has invalid severity: {bc.severity}"
