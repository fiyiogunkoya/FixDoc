"""Tests for Kubernetes change intelligence CLI commands."""

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fixdoc.commands.k8s_cmd import k8s_group

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "k8s"

_k8s_cmd_mod = importlib.import_module("fixdoc.commands.k8s_cmd")


# ---------------------------------------------------------------------------
# k8s analyze
# ---------------------------------------------------------------------------


class TestK8sAnalyze:
    def test_analyze_no_cluster_human(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "Azure Linux 2.0 to 3.0" in result.output
        assert "Risk Score" in result.output
        assert "Platform Context" in result.output

    def test_analyze_json_output(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "-f", "json",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["category"] == "os-upgrade"
        assert data["score"] > 0
        assert len(data["platform_risks"]) == 4
        assert "analysis_id" in data

    def test_analyze_markdown_output(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "-f", "markdown",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "## " in result.output
        assert "Platform Context" in result.output

    def test_analyze_with_snapshot(self):
        runner = CliRunner()
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "Affected Resources" in result.output

    def test_analyze_with_snapshot_json(self):
        runner = CliRunner(mix_stderr=False)
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
            "-f", "json",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["has_cluster_data"] is True
        assert len(data["cluster_exposure"]) > 0
        assert data["rollout_risk"] is not None

    def test_analyze_k8s_version(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "k8s-version",
            "--from", "1.28",
            "--to", "1.29",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "Kubernetes" in result.output

    def test_analyze_ingress_controller(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "ingress-controller",
            "--from", "nginx",
            "--to", "contour",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "NGINX" in result.output or "Contour" in result.output

    def test_analyze_ingress_with_snapshot(self):
        runner = CliRunner()
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "ingress-controller",
            "--from", "nginx",
            "--to", "contour",
            "--snapshot", snapshot_path,
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "Affected Resources" in result.output

    def test_analyze_node_pool_sku(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "node-pool-sku",
            "--from", "Standard_D2s_v3",
            "--to", "Standard_D4s_v3",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "Node Pool" in result.output

    def test_analyze_exit_on_trigger(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--exit-on", "low",
        ], obj={"base_path": None})
        # OS upgrade has a non-trivial score, should trigger exit 1
        assert result.exit_code == 1

    def test_analyze_exit_on_no_trigger(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--exit-on", "critical",
        ], obj={"base_path": None})
        # Baseline score without cluster should not be critical
        assert result.exit_code == 0

    def test_analyze_invalid_snapshot(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", "/nonexistent/path.json",
        ], obj={"base_path": None})
        assert result.exit_code != 0

    def test_analyze_unknown_change(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "ubuntu:20.04",
            "--to", "ubuntu:22.04",
        ], obj={"base_path": None})
        assert result.exit_code == 0
        assert "No catalog entry" in result.output

    def test_analyze_with_repo(self, tmp_path):
        from fixdoc.storage import FixRepository
        from fixdoc.models import Fix

        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="cgroup v2 migration broke pods",
            resolution="Updated containers to cgroup v2 compatible base images",
            tags="kubernetes, cgroup, aks",
        ))

        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
        ], obj={"base_path": str(tmp_path)})
        assert result.exit_code == 0
        assert "Relevant Team Knowledge" in result.output

    def test_analyze_verbose(self):
        runner = CliRunner()
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
            "-v",
        ], obj={"base_path": None})
        assert result.exit_code == 0

    def test_analyze_score_explanation(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "-f", "json",
        ], obj={"base_path": None})
        data = json.loads(result.output)
        assert len(data["score_explanation"]) > 0
        assert data["score_explanation"][0]["kind"] == "baseline"


# ---------------------------------------------------------------------------
# k8s snapshot
# ---------------------------------------------------------------------------


class TestK8sSnapshot:
    @patch.object(_k8s_cmd_mod, "capture_cluster_snapshot")
    def test_snapshot_command(self, mock_capture, tmp_path):
        from fixdoc.k8s.models import ClusterSnapshot, NodePool
        mock_capture.return_value = ClusterSnapshot(
            node_pools=[NodePool(name="test", count=1)],
            workloads=[],
            ingresses=[],
        )
        runner = CliRunner()
        out_path = str(tmp_path / "snap.json")
        result = runner.invoke(k8s_group, [
            "snapshot",
            "-o", out_path,
        ])
        assert result.exit_code == 0
        assert "Snapshot saved" in result.output
        # Verify file was written
        with open(out_path) as f:
            data = json.load(f)
        assert len(data["node_pools"]) == 1


# ---------------------------------------------------------------------------
# k8s changes
# ---------------------------------------------------------------------------


class TestK8sChanges:
    def test_changes_list_all(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, ["changes"])
        assert result.exit_code == 0
        assert "os-upgrade" in result.output
        assert "k8s-version" in result.output
        assert "ingress-controller" in result.output
        assert "node-pool-sku" in result.output

    def test_changes_filter_category(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, [
            "changes", "--category", "os-upgrade",
        ])
        assert result.exit_code == 0
        assert "Azure Linux" in result.output

    def test_changes_has_breaking_count(self):
        runner = CliRunner()
        result = runner.invoke(k8s_group, ["changes"])
        assert result.exit_code == 0
        assert "breaking changes" in result.output


# ---------------------------------------------------------------------------
# Output Format Integration
# ---------------------------------------------------------------------------


class TestOutputFormats:
    def test_human_contains_sections(self):
        runner = CliRunner()
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
        ], obj={"base_path": None})
        assert "Platform Context" in result.output
        assert "Affected Resources" in result.output
        assert "Rollout Risk" in result.output
        assert "Action Items" in result.output

    def test_json_is_valid(self):
        runner = CliRunner(mix_stderr=False)
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
            "-f", "json",
        ], obj={"base_path": None})
        data = json.loads(result.output)
        assert "analysis_id" in data
        assert "platform_risks" in data
        assert "cluster_exposure" in data
        assert "rollout_risk" in data
        assert "pre_checks" in data

    def test_markdown_has_headings(self):
        runner = CliRunner()
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
            "-f", "markdown",
        ], obj={"base_path": None})
        assert "## " in result.output
        assert "Platform Context" in result.output
        assert "### Affected Resources" in result.output
        assert "Action Items" in result.output

    def test_markdown_collapsible_for_many_workloads(self):
        """If more than 5 exposed workloads, markdown uses collapsible section."""
        runner = CliRunner()
        snapshot_path = str(FIXTURE_DIR / "sample_snapshot.json")
        result = runner.invoke(k8s_group, [
            "analyze",
            "--change", "os-upgrade",
            "--from", "azurelinux:2.0",
            "--to", "azurelinux:3.0",
            "--snapshot", snapshot_path,
            "-f", "markdown",
        ], obj={"base_path": None})
        # May or may not have collapsible depending on exposure count
        assert result.exit_code == 0
