"""Tests for the fixdoc blast-radius feature."""

import importlib
import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from fixdoc.blast_radius import (
    classify_control_point,
    parse_dot_graph,
    compute_affected_set,
    compute_blast_score,
    severity_label,
    compute_history_prior,
    redact_plan_values,
    generate_checks,
    analyze_blast_radius,
    BlastNode,
    BlastResult,
    _normalize_tf_node,
)
from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig
from fixdoc.models import Fix
from fixdoc.storage import FixRepository

# Get the actual command module for subprocess patching
_br_cmd_mod = importlib.import_module("fixdoc.commands.blast_radius")


def make_obj(tmp_path):
    """Create a ctx.obj dict for test invocations."""
    return {
        "base_path": tmp_path,
        "config": FixDocConfig(),
        "config_manager": MagicMock(),
    }


def make_plan(resource_changes=None):
    """Create a minimal Terraform plan dict."""
    return {"resource_changes": resource_changes or []}


def make_resource_change(address, resource_type, actions, provider_name=""):
    """Create a resource_change entry for a plan."""
    return {
        "address": address,
        "type": resource_type,
        "name": address.split(".")[-1] if "." in address else address,
        "provider_name": provider_name,
        "change": {
            "actions": actions,
            "after": {},
        },
    }


# ===================================================================
# TestControlPointClassification
# ===================================================================


class TestControlPointClassification:
    """Tests for control-point prefix matching and criticality."""

    def test_aws_iam_role(self):
        result = classify_control_point("aws_iam_role")
        assert result is not None
        assert result[0] == "iam"
        assert result[1] == 0.9

    def test_aws_iam_policy(self):
        result = classify_control_point("aws_iam_policy")
        assert result is not None
        assert result[0] == "iam"

    def test_aws_iam_role_policy_attachment(self):
        result = classify_control_point("aws_iam_role_policy_attachment")
        assert result is not None
        assert result[0] == "iam"
        assert result[1] == 0.9

    def test_azure_role_assignment(self):
        result = classify_control_point("azurerm_role_assignment")
        assert result is not None
        assert result[0] == "rbac"
        assert result[1] == 0.9

    def test_gcp_iam_prefix_match(self):
        """google_project_iam_member matches google_project_iam prefix."""
        result = classify_control_point("google_project_iam_member")
        assert result is not None
        assert result[0] == "iam"
        assert result[1] == 0.9

    def test_gcp_service_account(self):
        result = classify_control_point("google_service_account")
        assert result is not None
        assert result[0] == "iam"

    def test_network_security_group(self):
        result = classify_control_point("aws_security_group")
        assert result is not None
        assert result[0] == "network"
        assert result[1] == 0.8

    def test_non_control_point_returns_none(self):
        result = classify_control_point("aws_s3_bucket")
        assert result is None

    def test_case_insensitive(self):
        result = classify_control_point("AWS_IAM_ROLE")
        assert result is not None
        assert result[0] == "iam"


# ===================================================================
# TestDotParser
# ===================================================================


class TestDotParser:
    """Tests for DOT graph parsing and node normalization."""

    def test_simple_quoted_edge(self):
        dot = '"aws_iam_role.app" -> "aws_lambda_function.api"'
        fwd, rev = parse_dot_graph(dot)
        assert "aws_lambda_function.api" in fwd.get("aws_iam_role.app", set())

    def test_unquoted_edge(self):
        dot = "nodeA -> nodeB"
        fwd, rev = parse_dot_graph(dot)
        assert "nodeB" in fwd.get("nodeA", set())

    def test_reverse_adjacency(self):
        dot = '"A" -> "B"'
        fwd, rev = parse_dot_graph(dot)
        assert "A" in rev.get("B", set())

    def test_normalize_root_prefix(self):
        assert _normalize_tf_node("[root] aws_iam_role.app") == "aws_iam_role.app"

    def test_normalize_expand_suffix(self):
        assert _normalize_tf_node("[root] module.app (expand)") == "module.app"

    def test_normalize_close_suffix(self):
        assert _normalize_tf_node("[root] module.app (close)") == "module.app"

    def test_ignores_comments(self):
        dot = '// this is a comment\n"A" -> "B"'
        fwd, rev = parse_dot_graph(dot)
        assert "B" in fwd.get("A", set())
        assert len(fwd) == 2  # A and B

    def test_ignores_subgraph(self):
        dot = 'subgraph cluster_0 {\n"A" -> "B"\n}'
        fwd, _ = parse_dot_graph(dot)
        assert "B" in fwd.get("A", set())

    def test_empty_input(self):
        fwd, rev = parse_dot_graph("")
        assert fwd == {}
        assert rev == {}

    def test_real_tf_snippet(self):
        dot = """digraph {
    "[root] aws_iam_role.app" -> "[root] provider.aws"
    "[root] aws_lambda_function.api" -> "[root] aws_iam_role.app"
}"""
        fwd, rev = parse_dot_graph(dot)
        assert "provider.aws" in fwd.get("aws_iam_role.app", set())
        assert "aws_iam_role.app" in fwd.get("aws_lambda_function.api", set())

    def test_multiple_edges_from_same_node(self):
        dot = '"A" -> "B"\n"A" -> "C"'
        fwd, _ = parse_dot_graph(dot)
        assert fwd["A"] == {"B", "C"}


# ===================================================================
# TestBFS
# ===================================================================


class TestBFS:
    """Tests for bounded BFS propagation."""

    def test_single_hop(self):
        adj = {"A": {"B"}, "B": set()}
        result = compute_affected_set(["A"], adj, max_depth=5)
        assert len(result) == 1
        assert result[0].address == "B"
        assert result[0].depth == 1

    def test_multi_hop(self):
        adj = {"A": {"B"}, "B": {"C"}, "C": set()}
        result = compute_affected_set(["A"], adj, max_depth=5)
        addrs = {r.address for r in result}
        assert addrs == {"B", "C"}

    def test_max_depth_respected(self):
        adj = {"A": {"B"}, "B": {"C"}, "C": {"D"}, "D": set()}
        result = compute_affected_set(["A"], adj, max_depth=2)
        addrs = {r.address for r in result}
        assert "B" in addrs
        assert "C" in addrs
        assert "D" not in addrs

    def test_cycle_safety(self):
        adj = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
        result = compute_affected_set(["A"], adj, max_depth=10)
        addrs = {r.address for r in result}
        assert addrs == {"B", "C"}

    def test_multiple_starts(self):
        adj = {"A": {"C"}, "B": {"C"}, "C": {"D"}, "D": set()}
        result = compute_affected_set(["A", "B"], adj, max_depth=5)
        addrs = {r.address for r in result}
        assert "C" in addrs
        assert "D" in addrs

    def test_disconnected_node(self):
        adj = {"A": {"B"}, "B": set(), "X": {"Y"}, "Y": set()}
        result = compute_affected_set(["A"], adj, max_depth=5)
        addrs = {r.address for r in result}
        assert addrs == {"B"}
        assert "X" not in addrs
        assert "Y" not in addrs


# ===================================================================
# TestBlastScore
# ===================================================================


class TestBlastScore:
    """Tests for blast score computation and severity labeling."""

    def test_zero_baseline(self):
        """No affected, no criticality, no-op action gives low score."""
        score = compute_blast_score(0, 0.0, ["no-op"], 0.0)
        assert score < 35

    def test_affected_count_increases_score(self):
        base = compute_blast_score(0, 0.5, ["update"], 0.0)
        more = compute_blast_score(10, 0.5, ["update"], 0.0)
        assert more > base

    def test_criticality_increases_score(self):
        low_crit = compute_blast_score(5, 0.3, ["update"], 0.0)
        high_crit = compute_blast_score(5, 0.9, ["update"], 0.0)
        assert high_crit > low_crit

    def test_delete_higher_than_create(self):
        delete_score = compute_blast_score(5, 0.5, ["delete"], 0.0)
        create_score = compute_blast_score(5, 0.5, ["create"], 0.0)
        assert delete_score > create_score

    def test_history_prior_increases_score(self):
        no_hist = compute_blast_score(5, 0.5, ["update"], 0.0)
        with_hist = compute_blast_score(5, 0.5, ["update"], 1.0)
        assert with_hist > no_hist

    def test_severity_critical(self):
        assert severity_label(85) == "critical"

    def test_severity_high(self):
        assert severity_label(65) == "high"

    def test_severity_medium(self):
        assert severity_label(50) == "medium"

    def test_severity_low(self):
        assert severity_label(20) == "low"


# ===================================================================
# TestRedaction
# ===================================================================


class TestRedaction:
    """Tests for plan value redaction."""

    def test_password_key_redacted(self):
        change = {"after": {"db_password": "secret123", "name": "mydb"}}
        result = redact_plan_values(change)
        assert result["after"]["db_password"] == "[REDACTED]"
        assert result["after"]["name"] == "mydb"

    def test_token_key_redacted(self):
        change = {"after": {"api_token": "tok_abc", "region": "us-east-1"}}
        result = redact_plan_values(change)
        assert result["after"]["api_token"] == "[REDACTED]"
        assert result["after"]["region"] == "us-east-1"

    def test_sensitive_values_markers(self):
        change = {
            "after": {"connection_string": "postgres://...", "name": "mydb"},
            "after_sensitive": {"connection_string": True},
        }
        result = redact_plan_values(change)
        assert result["after"]["connection_string"] == "[REDACTED]"
        assert result["after"]["name"] == "mydb"

    def test_nested_values(self):
        change = {
            "after": {
                "config": {"secret_key": "abc", "timeout": 30}
            }
        }
        result = redact_plan_values(change)
        assert result["after"]["config"]["secret_key"] == "[REDACTED]"
        assert result["after"]["config"]["timeout"] == 30

    def test_non_sensitive_preserved(self):
        change = {"after": {"name": "myapp", "region": "us-west-2"}}
        result = redact_plan_values(change)
        assert result["after"]["name"] == "myapp"
        assert result["after"]["region"] == "us-west-2"


# ===================================================================
# TestHistoryPrior
# ===================================================================


class TestHistoryPrior:
    """Tests for history-prior scoring."""

    def test_matching_fixes(self, tmp_path):
        repo = FixRepository(tmp_path)
        repo.save(Fix(issue="IAM role issue", resolution="Fixed it", tags="aws_iam_role"))
        prior, matches = compute_history_prior(["aws_iam_role"], repo)
        assert prior > 0.0
        assert len(matches) == 1

    def test_no_matches(self, tmp_path):
        repo = FixRepository(tmp_path)
        prior, matches = compute_history_prior(["aws_s3_bucket"], repo)
        assert prior == 0.0
        assert len(matches) == 0

    def test_capped_at_one(self, tmp_path):
        repo = FixRepository(tmp_path)
        for i in range(5):
            repo.save(Fix(issue=f"Issue {i}", resolution="Fix", tags="aws_iam_role"))
        prior, matches = compute_history_prior(["aws_iam_role"], repo)
        assert prior == 1.0

    def test_multiple_resource_types(self, tmp_path):
        repo = FixRepository(tmp_path)
        repo.save(Fix(issue="IAM issue", resolution="Fix", tags="aws_iam_role"))
        repo.save(Fix(issue="SG issue", resolution="Fix", tags="aws_security_group"))
        prior, matches = compute_history_prior(
            ["aws_iam_role", "aws_security_group"], repo
        )
        assert len(matches) == 2


# ===================================================================
# TestGenerateChecks
# ===================================================================


class TestGenerateChecks:
    """Tests for recommended check generation."""

    def test_iam_checks(self):
        cps = [BlastNode("a", "aws_iam_role", "delete", category="iam", criticality=0.9)]
        checks = generate_checks(cps, has_deletes=False)
        assert any("IAM" in c for c in checks)

    def test_network_checks(self):
        cps = [BlastNode("a", "aws_security_group", "update", category="network", criticality=0.8)]
        checks = generate_checks(cps, has_deletes=False)
        assert any("security group" in c for c in checks)

    def test_delete_check_added(self):
        cps = [BlastNode("a", "aws_iam_role", "delete", category="iam", criticality=0.9)]
        checks = generate_checks(cps, has_deletes=True)
        assert any("not referenced" in c for c in checks)

    def test_no_duplicates_same_category(self):
        cps = [
            BlastNode("a", "aws_iam_role", "delete", category="iam", criticality=0.9),
            BlastNode("b", "aws_iam_policy", "update", category="iam", criticality=0.85),
        ]
        checks = generate_checks(cps, has_deletes=False)
        iam_checks = [c for c in checks if "IAM" in c]
        # Should only have 2 IAM checks (not 4 from duplicate category)
        assert len(iam_checks) == 1


# ===================================================================
# TestBlastRadiusCommand
# ===================================================================


class TestBlastRadiusCommand:
    """Tests for the CLI command."""

    def _write_plan(self, tmp_path, plan_data):
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan_data))
        return str(plan_file)

    def test_human_format_output(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_iam_role.app", "aws_iam_role", ["delete"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        runner = CliRunner()
        cli = create_cli()

        with patch.object(_br_cmd_mod, "_auto_run_terraform_graph", return_value=None):
            result = runner.invoke(
                cli,
                ["blast-radius", plan_file],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0
        assert "Blast Radius Analysis" in result.output
        assert "Score:" in result.output

    def test_json_format_output(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_iam_role.app", "aws_iam_role", ["delete"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        runner = CliRunner(mix_stderr=False)
        cli = create_cli()

        with patch.object(_br_cmd_mod, "_auto_run_terraform_graph", return_value=None):
            result = runner.invoke(
                cli,
                ["blast-radius", plan_file, "--format", "json"],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "score" in data
        assert "severity" in data
        assert "control_points" in data

    def test_no_control_points(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_s3_bucket.data", "aws_s3_bucket", ["create"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        runner = CliRunner()
        cli = create_cli()

        with patch.object(_br_cmd_mod, "_auto_run_terraform_graph", return_value=None):
            result = runner.invoke(
                cli,
                ["blast-radius", plan_file],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0
        assert "Changed Control Points" not in result.output

    def test_graph_flag(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_iam_role.app", "aws_iam_role", ["delete"]),
            make_resource_change("aws_lambda_function.api", "aws_lambda_function", ["update"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        dot_file = tmp_path / "graph.dot"
        dot_file.write_text('"aws_iam_role.app" -> "aws_lambda_function.api"')

        runner = CliRunner()
        cli = create_cli()

        result = runner.invoke(
            cli,
            ["blast-radius", plan_file, "--graph", str(dot_file)],
            obj=make_obj(tmp_path),
        )

        assert result.exit_code == 0

    def test_auto_terraform_graph(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_iam_role.app", "aws_iam_role", ["delete"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        runner = CliRunner()
        cli = create_cli()

        with patch.object(_br_cmd_mod, "_auto_run_terraform_graph", return_value='"A" -> "B"'):
            result = runner.invoke(
                cli,
                ["blast-radius", plan_file],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0

    def test_terraform_not_on_path(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_iam_role.app", "aws_iam_role", ["delete"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        runner = CliRunner()
        cli = create_cli()

        with patch.object(_br_cmd_mod, "_auto_run_terraform_graph", return_value=None):
            result = runner.invoke(
                cli,
                ["blast-radius", plan_file],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0

    def test_invalid_json(self, tmp_path):
        plan_file = tmp_path / "bad.json"
        plan_file.write_text("not json at all {{{")

        runner = CliRunner()
        cli = create_cli()

        result = runner.invoke(
            cli,
            ["blast-radius", str(plan_file)],
            obj=make_obj(tmp_path),
        )

        assert result.exit_code == 1

    def test_max_depth_option(self, tmp_path):
        plan = make_plan([
            make_resource_change("aws_iam_role.app", "aws_iam_role", ["delete"]),
        ])
        plan_file = self._write_plan(tmp_path, plan)

        runner = CliRunner()
        cli = create_cli()

        with patch.object(_br_cmd_mod, "_auto_run_terraform_graph", return_value=None):
            result = runner.invoke(
                cli,
                ["blast-radius", plan_file, "--max-depth", "2"],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0


# ===================================================================
# TestEndToEnd
# ===================================================================


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_iam_delete_scenario(self, tmp_path):
        """Full IAM role deletion with graph and history."""
        repo = FixRepository(tmp_path)
        repo.save(Fix(
            issue="IAM role deletion broke Lambda functions",
            resolution="Recreated role with matching policy",
            tags="aws_iam_role,aws,iam",
        ))

        plan = make_plan([
            make_resource_change("aws_iam_role.app_role", "aws_iam_role", ["delete"]),
            make_resource_change("aws_lambda_function.api", "aws_lambda_function", ["update"]),
        ])

        dot = """digraph {
    "aws_lambda_function.api" -> "aws_iam_role.app_role"
}"""

        result = analyze_blast_radius(plan, repo, dot_text=dot, max_depth=5)

        assert result.score > 0
        assert result.severity in ("low", "medium", "high", "critical")
        assert len(result.control_points) == 1
        assert result.control_points[0]["address"] == "aws_iam_role.app_role"
        assert len(result.history_matches) >= 1
        assert len(result.checks) > 0

    def test_network_change_scenario(self, tmp_path):
        """Security group modification with downstream resources."""
        repo = FixRepository(tmp_path)

        plan = make_plan([
            make_resource_change("aws_security_group.main", "aws_security_group", ["update"]),
            make_resource_change("aws_instance.web", "aws_instance", ["update"]),
        ])

        dot = """digraph {
    "aws_instance.web" -> "aws_security_group.main"
}"""

        result = analyze_blast_radius(plan, repo, dot_text=dot, max_depth=5)

        assert result.score > 0
        assert len(result.control_points) == 1
        assert result.control_points[0]["category"] == "network"
        assert any("security group" in c for c in result.checks)

    def test_no_changes_scenario(self, tmp_path):
        """Plan with only no-op changes has low score."""
        repo = FixRepository(tmp_path)

        plan = make_plan([
            make_resource_change("aws_s3_bucket.data", "aws_s3_bucket", ["no-op"]),
        ])

        result = analyze_blast_radius(plan, repo)

        assert result.score < 35
        assert result.severity == "low"
        assert len(result.control_points) == 0
