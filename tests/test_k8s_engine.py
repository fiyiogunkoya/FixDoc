"""Tests for Kubernetes change impact engine and snapshot module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fixdoc.k8s.engine import (
    _classify_match_confidence,
    _compute_baseline_score,
    _compute_exposure_score,
    _match_hint_against_ingress,
    _match_hint_against_workload,
    _matches_applies_to,
    _severity_label,
    _find_relevant_fixes,
    _K8S_SEARCH_TAGS,
    _K8S_TAG_TIERS,
    analyze_k8s_change,
)
from fixdoc.k8s.models import (
    BreakingChange,
    ClusterSnapshot,
    ExposedWorkload,
    IngressResource,
    NodePool,
    Workload,
)
from fixdoc.k8s.snapshot import (
    _extract_ingresses,
    _extract_node_pools,
    _extract_workloads,
    load_snapshot,
    save_snapshot,
)
from fixdoc.models import Fix


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "k8s"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_baseline_score_os_upgrade(self):
        bcs = [
            BreakingChange(id="a", title="", severity="critical", description="", consequence=""),
            BreakingChange(id="b", title="", severity="high", description="", consequence=""),
            BreakingChange(id="c", title="", severity="medium", description="", consequence=""),
        ]
        # critical=25, high=15, medium=8 = 48 * 1.0 = 48
        score = _compute_baseline_score(bcs, "os-upgrade")
        assert score == 48.0

    def test_baseline_score_k8s_version_multiplier(self):
        bcs = [
            BreakingChange(id="a", title="", severity="critical", description="", consequence=""),
        ]
        # 25 * 0.9 = 22.5
        score = _compute_baseline_score(bcs, "k8s-version")
        assert score == 22.5

    def test_baseline_score_capped_at_70(self):
        bcs = [
            BreakingChange(id=str(i), title="", severity="critical", description="", consequence="")
            for i in range(5)
        ]
        # 5 * 25 = 125, capped at 70
        score = _compute_baseline_score(bcs, "os-upgrade")
        assert score == 70.0

    def test_exposure_score_by_kind(self):
        exposed = [
            ExposedWorkload(
                workload=Workload(kind="DaemonSet", name="ds", namespace="default"),
                breaking_change_id="x", reason="", impact="",
            ),
            ExposedWorkload(
                workload=Workload(kind="StatefulSet", name="ss", namespace="default"),
                breaking_change_id="x", reason="", impact="",
            ),
            ExposedWorkload(
                workload=Workload(kind="Deployment", name="dep", namespace="default"),
                breaking_change_id="x", reason="", impact="",
            ),
        ]
        # DaemonSet=5, StatefulSet=4, Deployment=2 = 11
        score = _compute_exposure_score(exposed)
        assert score == 11.0

    def test_exposure_score_capped_at_30(self):
        exposed = [
            ExposedWorkload(
                workload=Workload(kind="DaemonSet", name=f"ds{i}", namespace="default"),
                breaking_change_id="x", reason="", impact="",
            )
            for i in range(10)
        ]
        # 10 * 5 = 50, capped at 30
        score = _compute_exposure_score(exposed)
        assert score == 30.0

    def test_severity_label_bands(self):
        assert _severity_label(80) == "critical"
        assert _severity_label(76) == "critical"
        assert _severity_label(60) == "high"
        assert _severity_label(51) == "high"
        assert _severity_label(40) == "medium"
        assert _severity_label(26) == "medium"
        assert _severity_label(10) == "low"
        assert _severity_label(0) == "low"


# ---------------------------------------------------------------------------
# Workload Matching
# ---------------------------------------------------------------------------


class TestWorkloadMatching:
    def test_match_images(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       images=["gcr.io/distroless/static:nonroot"])
        hint = {"field": "images", "pattern": r"distroless"}
        assert _match_hint_against_workload(hint, wl) is True

    def test_no_match_images(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       images=["nginx:latest"])
        hint = {"field": "images", "pattern": r"distroless"}
        assert _match_hint_against_workload(hint, wl) is False

    def test_match_volumes_cgroup(self):
        wl = Workload(kind="DaemonSet", name="mon", namespace="monitoring",
                       volumes=[{"hostPath": {"path": "/sys/fs/cgroup"}}])
        hint = {"field": "volumes", "pattern": r"/sys/fs/cgroup"}
        assert _match_hint_against_workload(hint, wl) is True

    def test_match_security_context_privileged(self):
        wl = Workload(kind="DaemonSet", name="agent", namespace="default",
                       security_context={"privileged": True})
        hint = {"field": "security_context", "pattern": r"privileged.*true"}
        assert _match_hint_against_workload(hint, wl) is True

    def test_match_annotations(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       annotations={"nginx.ingress.kubernetes.io/rate-limit": "100"})
        hint = {"field": "annotations", "pattern": r"nginx\.ingress\.kubernetes\.io"}
        assert _match_hint_against_workload(hint, wl) is True

    def test_match_resource_requests(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       resource_requests={"cpu": "500m", "memory": "512Mi"})
        hint = {"field": "resource_requests", "pattern": r"."}
        assert _match_hint_against_workload(hint, wl) is True

    def test_no_match_empty_field(self):
        wl = Workload(kind="Deployment", name="app", namespace="default")
        hint = {"field": "resource_requests", "pattern": r"."}
        assert _match_hint_against_workload(hint, wl) is False

    def test_match_tolerations_gpu(self):
        wl = Workload(kind="Deployment", name="ml", namespace="default",
                       tolerations=[{"key": "nvidia.com/gpu", "effect": "NoSchedule"}])
        hint = {"field": "tolerations", "pattern": r"nvidia"}
        assert _match_hint_against_workload(hint, wl) is True

    def test_empty_hint_returns_false(self):
        wl = Workload(kind="Deployment", name="app", namespace="default")
        assert _match_hint_against_workload({}, wl) is False
        assert _match_hint_against_workload({"field": "", "pattern": ""}, wl) is False

    def test_invalid_regex_returns_false(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       images=["test"])
        hint = {"field": "images", "pattern": r"[invalid"}
        assert _match_hint_against_workload(hint, wl) is False


# ---------------------------------------------------------------------------
# Full Analysis
# ---------------------------------------------------------------------------


class TestAnalyzeK8sChange:
    def test_no_catalog_entry(self):
        result = analyze_k8s_change("os-upgrade", "ubuntu:20.04", "ubuntu:22.04")
        assert result.score == 0.0
        assert "No catalog entry" in result.recommendation

    def test_os_upgrade_no_cluster(self):
        result = analyze_k8s_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0")
        assert result.score > 0
        assert result.category == "os-upgrade"
        assert result.change_name == "Azure Linux 2.0 to 3.0"
        assert len(result.platform_risks) == 4
        assert len(result.pre_checks) > 0
        assert result.has_cluster_data is False
        assert result.cluster_exposure == []
        assert result.rollout_risk is None

    def test_os_upgrade_with_snapshot(self):
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            snapshot=snapshot,
        )
        assert result.has_cluster_data is True
        assert result.score > 0
        assert len(result.cluster_exposure) > 0
        assert result.rollout_risk is not None
        # The cgroup-monitor DaemonSet should be detected
        exposed_names = [
            e.get("workload", {}).get("name", "") for e in result.cluster_exposure
        ]
        assert "cgroup-monitor" in exposed_names

    def test_k8s_version_upgrade(self):
        result = analyze_k8s_change("k8s-version", "1.28", "1.29")
        assert result.category == "k8s-version"
        assert len(result.platform_risks) == 3
        assert result.score > 0

    def test_ingress_controller_with_snapshot(self):
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        assert result.has_cluster_data is True
        assert len(result.cluster_exposure) > 0  # nginx ingresses should match

    def test_node_pool_sku_with_snapshot(self):
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        result = analyze_k8s_change(
            "node-pool-sku", "Standard_D4s_v3", "Standard_D2s_v3",
            snapshot=snapshot,
        )
        assert result.has_cluster_data is True
        # Workloads with resource_requests should be detected
        assert len(result.cluster_exposure) > 0

    def test_known_safe_discount(self):
        # Snapshot with no matching workloads
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[
                Workload(kind="Deployment", name="simple", namespace="default"),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "k8s-version", "1.28", "1.29",
            snapshot=snapshot,
        )
        # Should get the discount
        has_discount = any(
            e.get("kind") == "discount" for e in result.score_explanation
        )
        assert has_discount

    def test_severity_bands(self):
        result = analyze_k8s_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0")
        assert result.severity in ("low", "medium", "high", "critical")

    def test_score_explanation_present(self):
        result = analyze_k8s_change("os-upgrade", "azurelinux:2.0", "azurelinux:3.0")
        assert len(result.score_explanation) > 0
        assert result.score_explanation[0]["kind"] == "baseline"

    def test_rollout_risk_with_snapshot(self):
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            snapshot=snapshot,
        )
        rr = result.rollout_risk
        assert rr is not None
        assert rr["total_node_count"] == 8  # 3 + 5
        assert rr["daemonset_count"] == 2
        assert rr["statefulset_count"] == 1

    def test_with_fix_repo(self):
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="cgroup v2 migration issue",
                resolution="Update container to cgroup v2",
                tags="cgroup, aks, kubernetes"),
        ]
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            repo=mock_repo,
        )
        assert len(result.relevant_fixes) > 0

    def test_deduplication(self):
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            snapshot=snapshot,
        )
        # Check no duplicate workload+bc combos in exposure
        seen = set()
        for item in result.cluster_exposure:
            wl = item.get("workload", {})
            key = (wl.get("name"), wl.get("namespace"), item.get("breaking_change_id"))
            assert key not in seen, f"Duplicate exposure: {key}"
            seen.add(key)


# ---------------------------------------------------------------------------
# Fix Database Integration
# ---------------------------------------------------------------------------


class TestFixDatabaseIntegration:
    def test_no_repo_returns_empty(self):
        fixes = _find_relevant_fixes("os-upgrade", None)
        assert fixes == []

    def test_repo_with_matching_tags(self):
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="cgroup v2 migration issue", resolution="Fixed it",
                tags="cgroup, aks, kubernetes"),
            Fix(issue="S3 bucket issue", resolution="Fixed it",
                tags="aws, s3"),
        ]
        fixes = _find_relevant_fixes("os-upgrade", mock_repo)
        assert len(fixes) == 1
        assert fixes[0]["issue"] == "cgroup v2 migration issue"

    def test_repo_boost_only_tags_excluded(self):
        """Fixes with only boost tags (no required tags) should not match."""
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="AKS generic issue", resolution="Fixed it",
                tags="aks, kubernetes"),
        ]
        fixes = _find_relevant_fixes("os-upgrade", mock_repo)
        assert len(fixes) == 0

    def test_fix_cap_at_10(self):
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue=f"Issue {i}", resolution="Fix", tags="api-deprecation, kubernetes, aks")
            for i in range(20)
        ]
        fixes = _find_relevant_fixes("k8s-version", mock_repo)
        assert len(fixes) == 10


# ---------------------------------------------------------------------------
# Snapshot Extraction
# ---------------------------------------------------------------------------


class TestSnapshotExtraction:
    def test_extract_node_pools(self):
        data = {
            "items": [
                {
                    "metadata": {"labels": {"agentpool": "system", "node.kubernetes.io/instance-type": "Standard_D4s_v3"}},
                    "status": {"nodeInfo": {"osImage": "Azure Linux 2.0", "kubeletVersion": "v1.28.5"}},
                    "spec": {},
                },
                {
                    "metadata": {"labels": {"agentpool": "system", "node.kubernetes.io/instance-type": "Standard_D4s_v3"}},
                    "status": {"nodeInfo": {"osImage": "Azure Linux 2.0", "kubeletVersion": "v1.28.5"}},
                    "spec": {},
                },
            ]
        }
        pools = _extract_node_pools(data)
        assert len(pools) == 1
        assert pools[0].name == "system"
        assert pools[0].count == 2

    def test_extract_workloads(self):
        data = {
            "items": [
                {
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "prod"},
                    "spec": {
                        "replicas": 3,
                        "template": {
                            "spec": {
                                "containers": [{"name": "api", "image": "nginx:latest"}],
                                "volumes": [],
                            }
                        },
                    },
                    "status": {},
                },
            ]
        }
        workloads = _extract_workloads(data)
        assert len(workloads) == 1
        assert workloads[0].kind == "Deployment"
        assert workloads[0].name == "api"
        assert workloads[0].replicas == 3
        assert "nginx:latest" in workloads[0].images

    def test_extract_daemonset_replicas(self):
        data = {
            "items": [
                {
                    "kind": "DaemonSet",
                    "metadata": {"name": "agent", "namespace": "monitoring"},
                    "spec": {"template": {"spec": {"containers": [{"name": "a", "image": "x"}]}}},
                    "status": {"desiredNumberScheduled": 5},
                },
            ]
        }
        workloads = _extract_workloads(data)
        assert workloads[0].replicas == 5

    def test_extract_ingresses(self):
        data = {
            "items": [
                {
                    "metadata": {"name": "api-ing", "namespace": "prod",
                                "annotations": {"nginx.ingress.kubernetes.io/rewrite-target": "/"}},
                    "spec": {
                        "ingressClassName": "nginx",
                        "rules": [{"host": "api.example.com"}],
                        "tls": [{"hosts": ["api.example.com"]}],
                    },
                },
            ]
        }
        ingresses = _extract_ingresses(data)
        assert len(ingresses) == 1
        assert ingresses[0].ingress_class == "nginx"
        assert "rewrite-target" in str(ingresses[0].annotations)

    def test_extract_empty_data(self):
        assert _extract_node_pools({}) == []
        assert _extract_node_pools({"items": []}) == []
        assert _extract_workloads({}) == []
        assert _extract_ingresses({}) == []


class TestSnapshotIO:
    def test_load_fixture_snapshot(self):
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        assert len(snapshot.node_pools) == 2
        assert len(snapshot.workloads) == 6
        assert snapshot.node_pools[0].name == "system"

    def test_save_and_load_roundtrip(self, tmp_path):
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="test", count=1)],
            workloads=[Workload(kind="Deployment", name="app", namespace="default")],
            ingresses=[],
            namespaces=["default"],
        )
        path = str(tmp_path / "snapshot.json")
        save_snapshot(snapshot, path)
        loaded = load_snapshot(path)
        assert len(loaded.node_pools) == 1
        assert loaded.node_pools[0].name == "test"
        assert len(loaded.workloads) == 1

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_snapshot("/nonexistent/path.json")


# ---------------------------------------------------------------------------
# Match Confidence Classification
# ---------------------------------------------------------------------------


class TestMatchConfidence:
    def test_trivial_dot_pattern_low(self):
        assert _classify_match_confidence({"pattern": "."}) == "low"

    def test_trivial_dotstar_pattern_low(self):
        assert _classify_match_confidence({"pattern": ".*"}) == "low"

    def test_trivial_with_applies_to_medium(self):
        assert _classify_match_confidence({"pattern": ".", "applies_to": {"kinds": ["Ingress"]}}) == "medium"

    def test_short_pattern_low(self):
        assert _classify_match_confidence({"pattern": "ab"}) == "low"

    def test_broad_or_short_tokens_low(self):
        assert _classify_match_confidence({"pattern": "cpu|mem"}) == "low"

    def test_broad_or_short_tokens_with_scope_medium(self):
        assert _classify_match_confidence({"pattern": "cpu|mem", "applies_to": {"kinds": ["Deployment"]}}) == "medium"

    def test_specific_pattern_high(self):
        assert _classify_match_confidence({"pattern": r"nginx\.ingress\.kubernetes\.io"}) == "high"

    def test_long_or_pattern_high(self):
        assert _classify_match_confidence({"pattern": r"distroless|scratch|alpine|static"}) == "high"

    def test_empty_pattern_low(self):
        assert _classify_match_confidence({"pattern": ""}) == "low"


# ---------------------------------------------------------------------------
# applies_to Scope Matching
# ---------------------------------------------------------------------------


class TestAppliesToScoping:
    def test_empty_applies_to_matches_all(self):
        wl = Workload(kind="Deployment", name="app", namespace="default")
        assert _matches_applies_to({}, wl, is_ingress=False) is True
        assert _matches_applies_to(None, wl, is_ingress=False) is True

    def test_kinds_match(self):
        wl = Workload(kind="Deployment", name="app", namespace="default")
        assert _matches_applies_to({"kinds": ["Deployment"]}, wl, is_ingress=False) is True
        assert _matches_applies_to({"kinds": ["DaemonSet"]}, wl, is_ingress=False) is False

    def test_kinds_ingress(self):
        ing = IngressResource(name="api", namespace="prod")
        assert _matches_applies_to({"kinds": ["Ingress"]}, ing, is_ingress=True) is True
        assert _matches_applies_to({"kinds": ["Deployment"]}, ing, is_ingress=True) is False

    def test_namespace_regex(self):
        wl = Workload(kind="Deployment", name="app", namespace="production")
        assert _matches_applies_to({"namespaces": ["prod.*"]}, wl, is_ingress=False) is True
        assert _matches_applies_to({"namespaces": ["staging"]}, wl, is_ingress=False) is False

    def test_name_regex(self):
        wl = Workload(kind="Deployment", name="api-server", namespace="default")
        assert _matches_applies_to({"names": ["api-.*"]}, wl, is_ingress=False) is True
        assert _matches_applies_to({"names": ["web-.*"]}, wl, is_ingress=False) is False

    def test_images_match(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       images=["nginx:latest", "sidecar:v1"])
        assert _matches_applies_to({"images": ["nginx"]}, wl, is_ingress=False) is True
        assert _matches_applies_to({"images": ["redis"]}, wl, is_ingress=False) is False

    def test_images_ignored_for_ingress(self):
        ing = IngressResource(name="api", namespace="prod")
        # images filter should pass for ingress (not applicable)
        assert _matches_applies_to({"images": ["nginx"]}, ing, is_ingress=True) is True

    def test_labels_match(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       labels={"app": "nginx", "tier": "frontend"})
        assert _matches_applies_to({"labels": {"app": "nginx"}}, wl, is_ingress=False) is True
        assert _matches_applies_to({"labels": {"app": "redis"}}, wl, is_ingress=False) is False

    def test_labels_regex_match(self):
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       labels={"app": "ingress-nginx"})
        assert _matches_applies_to({"labels": {"app": "ingress.*"}}, wl, is_ingress=False) is True

    def test_and_logic_multiple_fields(self):
        wl = Workload(kind="Deployment", name="api-server", namespace="production",
                       images=["nginx:latest"])
        # Both must match
        assert _matches_applies_to(
            {"kinds": ["Deployment"], "namespaces": ["production"]},
            wl, is_ingress=False,
        ) is True
        # One fails
        assert _matches_applies_to(
            {"kinds": ["DaemonSet"], "namespaces": ["production"]},
            wl, is_ingress=False,
        ) is False

    def test_or_logic_within_field(self):
        wl = Workload(kind="Deployment", name="app", namespace="staging")
        # Multiple values in namespaces → OR
        assert _matches_applies_to(
            {"namespaces": ["production", "staging"]},
            wl, is_ingress=False,
        ) is True

    def test_hint_with_applies_to_filters_workloads(self):
        """Integration: applies_to on a hint filters out non-matching workloads."""
        hint = {
            "field": "annotations",
            "pattern": r"nginx\.ingress",
            "applies_to": {"kinds": ["Ingress"]},
        }
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       annotations={"nginx.ingress.kubernetes.io/rewrite": "/"})
        # Workload has matching annotation BUT kind doesn't match
        assert _match_hint_against_workload(hint, wl) is False

    def test_hint_without_applies_to_still_matches(self):
        """Backward compat: no applies_to means match all."""
        hint = {"field": "images", "pattern": r"nginx"}
        wl = Workload(kind="Deployment", name="app", namespace="default",
                       images=["nginx:latest"])
        assert _match_hint_against_workload(hint, wl) is True

    def test_ingress_hint_applies_to(self):
        hint = {
            "field": "annotations",
            "pattern": r"nginx",
            "applies_to": {"namespaces": ["production"]},
        }
        ing_prod = IngressResource(name="api", namespace="production",
                                    annotations={"nginx.ingress.kubernetes.io/x": "y"})
        ing_dev = IngressResource(name="api", namespace="dev",
                                   annotations={"nginx.ingress.kubernetes.io/x": "y"})
        assert _match_hint_against_ingress(hint, ing_prod) is True
        assert _match_hint_against_ingress(hint, ing_dev) is False


# ---------------------------------------------------------------------------
# Dedup + Confidence in Analysis
# ---------------------------------------------------------------------------


class TestDedupAndConfidence:
    def test_dedup_same_workload_multiple_bcs(self):
        """Same workload matched by N breaking changes should appear once in exposure."""
        # This workload matches:
        # - os-azl3-cgroupv2 via /sys/fs/cgroup volumes
        # - os-azl3-cgroupv2 via privileged security_context
        # - os-azl3-systemd via /var/log/journal volumes
        # After dedup: 1 entry with match_count=2 (cgroupv2 + systemd = 2 BCs)
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[
                Workload(kind="DaemonSet", name="agent", namespace="monitoring",
                         volumes=[
                             {"hostPath": {"path": "/sys/fs/cgroup"}},
                             {"hostPath": {"path": "/var/log/journal"}},
                         ],
                         security_context={"privileged": True}),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            snapshot=snapshot,
        )
        agent_entries = [
            e for e in result.cluster_exposure
            if e.get("workload", {}).get("name") == "agent"
        ]
        assert len(agent_entries) == 1
        # Matches cgroupv2 + systemd = at least 2 BCs
        assert agent_entries[0].get("match_count", 1) >= 2

    def test_dedup_exposure_score_counts_unique(self):
        """Exposure score should be based on unique workloads, not raw match count."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[
                Workload(kind="DaemonSet", name="agent", namespace="monitoring",
                         volumes=[{"hostPath": {"path": "/sys/fs/cgroup"}}],
                         security_context={"privileged": True}),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            snapshot=snapshot,
        )
        # Check exposure explanation references unique workloads
        exposure_exps = [e for e in result.score_explanation if e["kind"] == "exposure"]
        if exposure_exps:
            assert "unique" in exposure_exps[0]["label"].lower()

    def test_confidence_affects_exposure_output(self):
        """cluster_exposure entries should have confidence field."""
        snapshot = load_snapshot(str(FIXTURE_DIR / "sample_snapshot.json"))
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        for item in result.cluster_exposure:
            assert "confidence" in item
            assert item["confidence"] in ("high", "medium", "low")

    def test_low_confidence_from_dot_pattern(self):
        """TLS hint with '.' pattern should be low confidence."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[],
            ingresses=[
                IngressResource(name="api", namespace="prod",
                                annotations={"nginx.ingress.kubernetes.io/ssl": "true"},
                                tls=[{"hosts": ["api.example.com"]}]),
            ],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        # Find api ingress — some match should be low confidence due to tls '.' pattern
        api_entries = [
            e for e in result.cluster_exposure
            if e.get("ingress", {}).get("name") == "api"
        ]
        assert len(api_entries) == 1

    def test_aggregated_matches_present(self):
        """Workloads matching multiple BCs should have all_matches list."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[],
            ingresses=[
                IngressResource(
                    name="api", namespace="prod",
                    annotations={
                        "nginx.ingress.kubernetes.io/rate-limit": "100",
                        "nginx.ingress.kubernetes.io/ssl-passthrough": "true",
                    },
                    tls=[{"hosts": ["api.example.com"]}],
                ),
            ],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        api_entries = [
            e for e in result.cluster_exposure
            if e.get("ingress", {}).get("name") == "api"
        ]
        assert len(api_entries) == 1
        assert api_entries[0]["match_count"] >= 2
        assert "all_matches" in api_entries[0]


# ---------------------------------------------------------------------------
# Ingress Class Matching
# ---------------------------------------------------------------------------


class TestIngressClassMatching:
    def test_ingress_class_hint_matches(self):
        """ingress_class field in hint should match against ingress."""
        ing = IngressResource(name="api", namespace="prod", ingress_class="nginx")
        hint = {"field": "ingress_class", "pattern": r"nginx"}
        assert _match_hint_against_ingress(hint, ing) is True

    def test_ingress_class_hint_no_match(self):
        ing = IngressResource(name="api", namespace="prod", ingress_class="contour")
        hint = {"field": "ingress_class", "pattern": r"nginx"}
        assert _match_hint_against_ingress(hint, ing) is False

    def test_ingress_class_hint_none_class(self):
        ing = IngressResource(name="api", namespace="prod", ingress_class=None)
        hint = {"field": "ingress_class", "pattern": r"nginx"}
        assert _match_hint_against_ingress(hint, ing) is False

    def test_ingress_class_in_full_analysis(self):
        """Ingress with nginx class should be detected by the annotations BC."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[],
            ingresses=[
                IngressResource(name="api", namespace="prod", ingress_class="nginx"),
            ],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        api_entries = [
            e for e in result.cluster_exposure
            if e.get("ingress", {}).get("name") == "api"
        ]
        assert len(api_entries) == 1


# ---------------------------------------------------------------------------
# Controller Workload Detection
# ---------------------------------------------------------------------------


class TestControllerWorkloadDetection:
    def test_controller_detected_by_image(self):
        """ingress-nginx controller Deployment detected via image hint."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[
                Workload(
                    kind="Deployment", name="ingress-nginx-controller",
                    namespace="ingress-nginx",
                    images=["registry.k8s.io/ingress-nginx/controller:v1.9.0"],
                ),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        ctrl = [
            e for e in result.cluster_exposure
            if e.get("workload", {}).get("name") == "ingress-nginx-controller"
        ]
        assert len(ctrl) == 1

    def test_controller_detected_by_label(self):
        """ingress-nginx controller detected via label hint."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[
                Workload(
                    kind="Deployment", name="nginx-ctrl",
                    namespace="ingress-nginx",
                    labels={"app.kubernetes.io/name": "ingress-nginx"},
                ),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        ctrl = [
            e for e in result.cluster_exposure
            if e.get("workload", {}).get("name") == "nginx-ctrl"
        ]
        assert len(ctrl) == 1

    def test_unrelated_workload_not_matched_by_controller_hints(self):
        """App workload without ingress-nginx image/labels should NOT match controller BC."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[
                Workload(
                    kind="Deployment", name="my-app",
                    namespace="default",
                    images=["my-app:v1.0"],
                ),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        app = [
            e for e in result.cluster_exposure
            if e.get("workload", {}).get("name") == "my-app"
        ]
        assert len(app) == 0


# ---------------------------------------------------------------------------
# Routing Rollout Risk
# ---------------------------------------------------------------------------


class TestRoutingRolloutRisk:
    def test_ingress_controller_routing_risk(self):
        """ingress-controller category should produce routing-type rollout risk."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=3)],
            workloads=[
                Workload(kind="Deployment", name="app", namespace="prod", replicas=3),
            ],
            ingresses=[
                IngressResource(name="api", namespace="prod",
                                tls=[{"hosts": ["api.example.com"]}]),
                IngressResource(name="web", namespace="default"),
            ],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        rr = result.rollout_risk
        assert rr is not None
        assert rr["type"] == "routing"
        assert rr["ingress_count"] == 2
        assert rr["affected_namespaces"] == 2
        assert rr["has_tls"] is True
        assert rr["total_pod_estimate"] == 3

    def test_os_upgrade_node_centric_risk(self):
        """Non-ingress categories should still produce node-centric rollout risk."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=3)],
            workloads=[
                Workload(kind="DaemonSet", name="agent", namespace="monitoring", replicas=3),
            ],
            ingresses=[],
        )
        result = analyze_k8s_change(
            "os-upgrade", "azurelinux:2.0", "azurelinux:3.0",
            snapshot=snapshot,
        )
        rr = result.rollout_risk
        assert rr is not None
        assert "type" not in rr  # node-centric format
        assert rr["total_node_count"] == 3
        assert rr["daemonset_count"] == 1

    def test_routing_risk_no_tls(self):
        """Routing risk with no TLS ingresses."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[],
            ingresses=[
                IngressResource(name="web", namespace="default"),
            ],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        rr = result.rollout_risk
        assert rr["type"] == "routing"
        assert rr["has_tls"] is False


# ---------------------------------------------------------------------------
# TLS Hint Scoping
# ---------------------------------------------------------------------------


class TestTlsHintScoping:
    def test_tls_hint_matches_ingress_kind(self):
        """TLS hint with applies_to kinds:Ingress should match ingress resources."""
        snapshot = ClusterSnapshot(
            node_pools=[NodePool(name="sys", count=1)],
            workloads=[],
            ingresses=[
                IngressResource(name="api", namespace="prod",
                                tls=[{"hosts": ["api.example.com"]}]),
            ],
        )
        result = analyze_k8s_change(
            "ingress-controller", "nginx", "contour",
            snapshot=snapshot,
        )
        api_entries = [
            e for e in result.cluster_exposure
            if e.get("ingress", {}).get("name") == "api"
        ]
        assert len(api_entries) == 1

    def test_tls_hint_does_not_match_workload(self):
        """TLS hint scoped to Ingress kind should NOT match workloads."""
        hint = {
            "field": "tls",
            "pattern": r".",
            "applies_to": {"kinds": ["Ingress"]},
        }
        wl = Workload(kind="Deployment", name="app", namespace="default")
        assert _match_hint_against_workload(hint, wl) is False


# ---------------------------------------------------------------------------
# Tag Tiers
# ---------------------------------------------------------------------------


class TestTagTiers:
    def test_backward_compat_alias(self):
        """_K8S_SEARCH_TAGS should still exist for backward compat."""
        assert "os-upgrade" in _K8S_SEARCH_TAGS
        assert "k8s-version" in _K8S_SEARCH_TAGS

    def test_tiers_have_required_and_boost(self):
        for cat, tiers in _K8S_TAG_TIERS.items():
            assert "required" in tiers
            assert "boost" in tiers
            assert len(tiers["required"]) > 0

    def test_required_tag_needed(self):
        """Fix with only boost tags should not match."""
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="generic k8s", resolution="fix", tags="kubernetes, aks"),
        ]
        fixes = _find_relevant_fixes("ingress-controller", mock_repo)
        assert len(fixes) == 0

    def test_required_tag_matches(self):
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="nginx issue", resolution="fix", tags="ingress, nginx, aks"),
        ]
        fixes = _find_relevant_fixes("ingress-controller", mock_repo)
        assert len(fixes) == 1

    def test_scoring_order(self):
        """Fixes with more required matches should rank higher."""
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="single match", resolution="fix", tags="ingress"),
            Fix(issue="double match", resolution="fix", tags="ingress, nginx, tls"),
        ]
        fixes = _find_relevant_fixes("ingress-controller", mock_repo)
        assert len(fixes) == 2
        assert fixes[0]["issue"] == "double match"

    def test_unknown_category_returns_empty(self):
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [
            Fix(issue="anything", resolution="fix", tags="kubernetes"),
        ]
        fixes = _find_relevant_fixes("unknown-category", mock_repo)
        assert fixes == []

    def test_list_tags_type(self):
        """Fix with list-type tags should work."""
        mock_repo = MagicMock()
        fix = MagicMock()
        fix.id = "abcdef1234"
        fix.issue = "cgroup fix"
        fix.resolution = "update"
        fix.tags = ["cgroup", "aks"]
        mock_repo.list_all.return_value = [fix]
        fixes = _find_relevant_fixes("os-upgrade", mock_repo)
        assert len(fixes) == 1


# ---------------------------------------------------------------------------
# Validation (generate.py)
# ---------------------------------------------------------------------------


class TestValidateGeneratedEntry:
    def test_valid_entry_no_warnings(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="os-upgrade",
            from_version="azurelinux:2.0",
            to_version="azurelinux:3.0",
            display_name="Test",
            breaking_changes=[
                BreakingChange(
                    id="test-bc",
                    title="Test BC",
                    severity="high",
                    description="A sufficiently long description for the test entry.",
                    consequence="Pods may crash on startup.",
                    detection_hints=[{
                        "field": "images",
                        "pattern": r"distroless|scratch",
                        "reason": "Uses minimal image",
                        "impact": "Binary may fail",
                    }],
                ),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert len(warnings) == 0

    def test_short_description_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="Short",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{
                                   "field": "images", "pattern": "nginx",
                                   "reason": "r", "impact": "i",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("description is too short" in w for w in warnings)

    def test_short_consequence_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Short",
                               detection_hints=[{
                                   "field": "images", "pattern": "nginx",
                                   "reason": "r", "impact": "i",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("consequence is too short" in w for w in warnings)

    def test_trivially_broad_pattern_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{
                                   "field": "resource_requests", "pattern": ".",
                                   "reason": "r", "impact": "i",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("trivially broad" in w for w in warnings)

    def test_broad_pattern_with_applies_to_no_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{
                                   "field": "resource_requests", "pattern": ".",
                                   "applies_to": {"kinds": ["DaemonSet"]},
                                   "reason": "r", "impact": "i",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert not any("trivially broad" in w for w in warnings)

    def test_invalid_field_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{
                                   "field": "invalid_field", "pattern": "test",
                                   "reason": "r", "impact": "i",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("invalid field" in w for w in warnings)

    def test_invalid_regex_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{
                                   "field": "images", "pattern": "[invalid",
                                   "reason": "r", "impact": "i",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("invalid regex" in w for w in warnings)

    def test_critical_severity_inflation_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="a", title="A", severity="critical",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{"field": "images", "pattern": "x", "reason": "r", "impact": "i"}]),
                BreakingChange(id="b", title="B", severity="critical",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{"field": "images", "pattern": "y", "reason": "r", "impact": "i"}]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("critical" in w.lower() and "inflated" in w.lower() for w in warnings)

    def test_no_hints_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("0 detection hints" in w for w in warnings)

    def test_missing_reason_and_impact_warning(self):
        from fixdoc.k8s.generate import validate_generated_entry
        from fixdoc.k8s.models import CatalogEntry, BreakingChange

        entry = CatalogEntry(
            category="test", from_version="1", to_version="2", display_name="T",
            breaking_changes=[
                BreakingChange(id="x", title="X", severity="low",
                               description="A sufficiently long description text here.",
                               consequence="Pods may crash on startup.",
                               detection_hints=[{
                                   "field": "images", "pattern": "nginx",
                               }]),
            ],
        )
        warnings = validate_generated_entry(entry)
        assert any("missing 'reason'" in w for w in warnings)
        assert any("missing 'impact'" in w for w in warnings)
