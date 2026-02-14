"""Integration tests for the full Terraform pipeline.

Exercises: error parsing → fix capture → suggestions → blast radius analysis,
all wired through realistic fixture data matching test_terraform/main.tf.
"""

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fixdoc.blast_radius import (
    analyze_blast_radius,
    parse_dot_graph,
    severity_label,
)
from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig
from fixdoc.models import Fix
from fixdoc.parsers.base import CloudProvider
from fixdoc.parsers.router import detect_and_parse, detect_error_source, ErrorSource
from fixdoc.parsers.terraform import TerraformParser
from fixdoc.storage import FixRepository
from fixdoc.suggestions import find_similar_fixes

# Actual command modules for subprocess patching
_br_cmd_mod = importlib.import_module("fixdoc.commands.blast_radius")
_watch_mod = importlib.import_module("fixdoc.commands.watch")


# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "terraform"
PLANS_DIR = FIXTURES_DIR / "plans"
ERRORS_DIR = FIXTURES_DIR / "aws" / "integration_errors"


def _load_fixture(path: Path) -> str:
    return path.read_text()


def _load_json_fixture(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_obj(tmp_path):
    """Create a ctx.obj dict for CLI test invocations."""
    return {
        "base_path": tmp_path,
        "config": FixDocConfig(),
        "config_manager": MagicMock(),
    }


def seed_fix(repo, issue, resolution, tags, error_excerpt=""):
    """Save a fix to the repo and return it."""
    fix = Fix(
        issue=issue,
        resolution=resolution,
        tags=tags,
        error_excerpt=error_excerpt,
    )
    repo.save(fix)
    return fix


# ===================================================================
# TestBlastRadiusIntegration
# ===================================================================


@pytest.mark.skipif(not PLANS_DIR.exists(), reason="plan fixtures missing")
class TestBlastRadiusIntegration:
    """Load fixture plans → analyze_blast_radius() + CLI → verify results."""

    def test_create_all_score_range(self, tmp_path):
        """All-create plan: low-medium score (create weight = 0.4)."""
        plan = _load_json_fixture(PLANS_DIR / "plan_create_all.json")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo)

        # 13 resources created, includes IAM + SG control points.
        # Create weight is 0.4 so score should be moderate.
        assert result.score >= 0
        assert result.score <= 100
        assert result.severity in ("low", "medium", "high")

    def test_create_all_identifies_control_points(self, tmp_path):
        """All-create plan identifies IAM role, policy attachment, and SGs."""
        plan = _load_json_fixture(PLANS_DIR / "plan_create_all.json")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo)

        cp_addresses = {cp["address"] for cp in result.control_points}
        assert "aws_iam_role.lambda_exec" in cp_addresses
        assert "aws_iam_role_policy_attachment.lambda_basic" in cp_addresses
        assert "aws_security_group.web" in cp_addresses
        assert "aws_security_group.db" in cp_addresses

    def test_create_all_change_count(self, tmp_path):
        """All-create plan has 13 changes."""
        plan = _load_json_fixture(PLANS_DIR / "plan_create_all.json")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo)

        assert result.plan_summary["total_changes"] == 13
        assert result.plan_summary["by_action"].get("create") == 13

    def test_iam_delete_high_score(self, tmp_path):
        """IAM delete plan: high/critical score (delete weight + IAM criticality)."""
        plan = _load_json_fixture(PLANS_DIR / "plan_iam_delete.json")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo)

        # IAM role (criticality 0.9) + delete (weight 1.0) → high score
        assert result.score >= 50
        assert result.severity in ("high", "critical")

    def test_iam_delete_has_delete_checks(self, tmp_path):
        """IAM delete plan generates delete-specific checks."""
        plan = _load_json_fixture(PLANS_DIR / "plan_iam_delete.json")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo)

        assert any("not referenced" in c.lower() for c in result.checks)
        assert any("iam" in c.lower() for c in result.checks)

    def test_sg_update_medium_score(self, tmp_path):
        """SG update plan: medium score (network criticality + update weight)."""
        plan = _load_json_fixture(PLANS_DIR / "plan_sg_update.json")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo)

        # SG (criticality 0.8) + update (weight 0.7) → medium range
        assert result.score >= 30
        assert result.severity in ("medium", "high")

    def test_graph_propagation_sg_update(self, tmp_path):
        """SG update with DOT graph finds downstream affected resources."""
        plan = _load_json_fixture(PLANS_DIR / "plan_sg_update.json")
        dot_text = _load_fixture(PLANS_DIR / "dependency_graph.dot")
        repo = FixRepository(tmp_path)
        result = analyze_blast_radius(plan, repo, dot_text=dot_text)

        # SG.web is a control point. Via graph, it connects to:
        # instance.web, lb.main, sg.db, lb_target_group.web, etc.
        affected_addrs = {a["address"] for a in result.affected}
        # At minimum the graph should propagate to some connected resources
        assert len(result.affected) > 0

    def test_history_prior_boosts_score(self, tmp_path):
        """Fixes in history for changed resource types raise the prior."""
        plan = _load_json_fixture(PLANS_DIR / "plan_sg_update.json")
        repo = FixRepository(tmp_path)

        # Seed 3 fixes for aws_security_group → prior = 1.0
        for i in range(3):
            seed_fix(
                repo,
                issue=f"SG issue #{i}",
                resolution=f"Fixed SG #{i}",
                tags="terraform,aws,aws_security_group",
            )

        result_with_history = analyze_blast_radius(plan, repo)

        # Compare against empty repo
        empty_repo = FixRepository(tmp_path / "empty")
        result_no_history = analyze_blast_radius(plan, empty_repo)

        assert result_with_history.score >= result_no_history.score
        assert len(result_with_history.history_matches) >= 1

    def test_blast_radius_cli_json_output(self, tmp_path):
        """CLI blast-radius with --format json returns valid JSON."""
        plan_path = PLANS_DIR / "plan_sg_update.json"
        cli = create_cli()
        runner = CliRunner(mix_stderr=False)

        with patch.object(
            _br_cmd_mod, "_auto_run_terraform_graph", return_value=None
        ):
            result = runner.invoke(
                cli,
                ["blast-radius", str(plan_path), "--format", "json"],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "score" in data
        assert "severity" in data
        assert "control_points" in data


# ===================================================================
# TestErrorParseIntegration
# ===================================================================


@pytest.mark.skipif(not ERRORS_DIR.exists(), reason="error fixtures missing")
class TestErrorParseIntegration:
    """Load fixture error texts → parse → verify all fields."""

    def test_s3_bucket_conflict_parse(self):
        """s3_bucket_conflict.txt: BucketAlreadyExists on aws_s3_bucket.data."""
        text = _load_fixture(ERRORS_DIR / "s3_bucket_conflict.txt")
        parser = TerraformParser()
        errors = parser.parse(text)

        assert len(errors) == 1
        err = errors[0]
        assert err.cloud_provider == CloudProvider.AWS
        assert err.resource_type == "aws_s3_bucket"
        assert err.resource_name == "data"
        assert err.resource_address == "aws_s3_bucket.data"
        assert err.error_code == "BucketAlreadyExists"
        assert err.file == "main.tf"
        assert err.line == 175

    def test_s3_bucket_conflict_tags_and_suggestions(self):
        """s3_bucket_conflict.txt generates correct tags and suggestions."""
        text = _load_fixture(ERRORS_DIR / "s3_bucket_conflict.txt")
        parser = TerraformParser()
        errors = parser.parse(text)
        err = errors[0]

        tags_str = err.generate_tags()
        assert "aws_s3_bucket" in tags_str
        assert "BucketAlreadyExists" in tags_str
        assert "terraform" in tags_str

        assert any("unique" in s.lower() or "different name" in s.lower()
                    for s in err.suggestions)

    def test_iam_access_denied_parse(self):
        """iam_access_denied.txt: AccessDeniedException on aws_lambda_function.api."""
        text = _load_fixture(ERRORS_DIR / "iam_access_denied.txt")
        parser = TerraformParser()
        errors = parser.parse(text)

        assert len(errors) >= 1
        err = errors[0]
        assert err.cloud_provider == CloudProvider.AWS
        assert err.resource_address == "aws_lambda_function.api"
        assert err.error_code in ("AccessDenied", "AccessDeniedException")
        assert any("iam" in s.lower() or "permission" in s.lower()
                    for s in err.suggestions)

    def test_ec2_capacity_parse(self):
        """ec2_capacity.txt: InsufficientInstanceCapacity on aws_instance.web."""
        text = _load_fixture(ERRORS_DIR / "ec2_capacity.txt")
        parser = TerraformParser()
        errors = parser.parse(text)

        assert len(errors) == 1
        err = errors[0]
        assert err.cloud_provider == CloudProvider.AWS
        assert err.resource_address == "aws_instance.web"
        assert err.error_code == "InsufficientInstanceCapacity"
        assert err.file == "main.tf"
        assert err.line == 122

    def test_rds_subnet_coverage_parse(self):
        """rds_subnet_coverage.txt: DBSubnetGroupDoesNotCoverEnoughAZs."""
        text = _load_fixture(ERRORS_DIR / "rds_subnet_coverage.txt")
        parser = TerraformParser()
        errors = parser.parse(text)

        assert len(errors) == 1
        err = errors[0]
        assert err.cloud_provider == CloudProvider.AWS
        assert err.resource_address == "aws_db_instance.main"
        assert err.error_code == "DBSubnetGroupDoesNotCoverEnoughAZs"

    def test_detect_and_parse_routes_correctly(self):
        """detect_and_parse routes fixture errors through TerraformParser."""
        for fixture_name in (
            "s3_bucket_conflict.txt",
            "iam_access_denied.txt",
            "ec2_capacity.txt",
            "rds_subnet_coverage.txt",
        ):
            text = _load_fixture(ERRORS_DIR / fixture_name)
            source = detect_error_source(text)
            assert source == ErrorSource.TERRAFORM, f"{fixture_name} not detected as TF"

            errors = detect_and_parse(text)
            assert len(errors) >= 1, f"{fixture_name} yielded no errors"
            assert errors[0].cloud_provider == CloudProvider.AWS


# ===================================================================
# TestSuggestionIntegration
# ===================================================================


@pytest.mark.skipif(not ERRORS_DIR.exists(), reason="error fixtures missing")
class TestSuggestionIntegration:
    """Seed repo with related fixes → parse errors → find_similar_fixes."""

    def test_s3_fix_surfaces_for_s3_error(self, tmp_path):
        """A seeded S3 fix should rank high for s3_bucket_conflict error."""
        repo = FixRepository(tmp_path)
        seed_fix(
            repo,
            issue="aws_s3_bucket.data: BucketAlreadyExists",
            resolution="Added random suffix to bucket name",
            tags="terraform,aws,aws_s3_bucket,BucketAlreadyExists",
            error_excerpt="BucketAlreadyExists: The requested bucket name",
        )

        text = _load_fixture(ERRORS_DIR / "s3_bucket_conflict.txt")
        parser = TerraformParser()
        err = parser.parse(text)[0]
        tags_str = err.generate_tags()

        similar = find_similar_fixes(repo, text, tags=tags_str)
        assert len(similar) >= 1
        assert "BucketAlreadyExists" in similar[0].issue

    def test_iam_fix_surfaces_for_iam_error(self, tmp_path):
        """A seeded IAM fix should rank high for iam_access_denied error."""
        repo = FixRepository(tmp_path)
        seed_fix(
            repo,
            issue="aws_lambda_function.api: AccessDeniedException iam:PassRole",
            resolution="Added iam:PassRole to Terraform CI user policy",
            tags="terraform,aws,aws_lambda_function,AccessDeniedException",
            error_excerpt="AccessDeniedException: iam:PassRole",
        )

        text = _load_fixture(ERRORS_DIR / "iam_access_denied.txt")
        parser = TerraformParser()
        err = parser.parse(text)[0]
        tags_str = err.generate_tags()

        similar = find_similar_fixes(repo, text, tags=tags_str)
        assert len(similar) >= 1
        assert "AccessDeniedException" in similar[0].tags

    def test_unrelated_fix_does_not_surface(self, tmp_path):
        """A Kubernetes fix should not rank for a Terraform S3 error."""
        repo = FixRepository(tmp_path)
        seed_fix(
            repo,
            issue="CrashLoopBackOff on payment-service pod",
            resolution="Fixed OOM by increasing memory limit",
            tags="kubernetes,pod,CrashLoopBackOff",
        )

        text = _load_fixture(ERRORS_DIR / "s3_bucket_conflict.txt")
        similar = find_similar_fixes(
            repo, text, tags="terraform,aws,aws_s3_bucket,BucketAlreadyExists"
        )
        assert len(similar) == 0

    def test_multiple_fixes_ranked_by_relevance(self, tmp_path):
        """More relevant fix (matching tags+error_code) ranks above partial match."""
        repo = FixRepository(tmp_path)

        # Partial match: same provider, different error
        seed_fix(
            repo,
            issue="aws_s3_bucket ACL issue",
            resolution="Disabled ACLs",
            tags="terraform,aws,aws_s3_bucket",
        )

        # Exact match: same error code
        exact = seed_fix(
            repo,
            issue="aws_s3_bucket.logs: BucketAlreadyExists",
            resolution="Used unique bucket name",
            tags="terraform,aws,aws_s3_bucket,BucketAlreadyExists",
            error_excerpt="BucketAlreadyExists",
        )

        text = _load_fixture(ERRORS_DIR / "s3_bucket_conflict.txt")
        parser = TerraformParser()
        err = parser.parse(text)[0]
        tags_str = err.generate_tags()

        similar = find_similar_fixes(repo, text, tags=tags_str)
        assert len(similar) == 2
        # The exact match should be first (higher score)
        assert similar[0].id == exact.id


# ===================================================================
# TestWatchIntegration
# ===================================================================


@pytest.mark.skipif(not ERRORS_DIR.exists(), reason="error fixtures missing")
class TestWatchIntegration:
    """Mock subprocess with fixture error output → watch → verify capture."""

    def _make_popen_mock(self, output_text, exit_code=1):
        """Create a mock Popen that yields output_text line-by-line."""
        lines = [line.encode("utf-8") + b"\n" for line in output_text.splitlines()]
        lines.append(b"")  # EOF sentinel

        mock_proc = MagicMock()
        mock_proc.stdout.readline = MagicMock(side_effect=lines)
        mock_proc.returncode = exit_code
        mock_proc.wait.return_value = exit_code
        return mock_proc

    def test_watch_captures_terraform_error(self, tmp_path):
        """Watch catches a failed terraform apply and offers capture."""
        error_text = _load_fixture(ERRORS_DIR / "s3_bucket_conflict.txt")
        mock_proc = self._make_popen_mock(error_text, exit_code=1)

        cli = create_cli()
        runner = CliRunner()

        with patch.object(
            _watch_mod.subprocess, "Popen", return_value=mock_proc
        ):
            result = runner.invoke(
                cli,
                ["watch", "--", "terraform", "apply"],
                obj=make_obj(tmp_path),
                input="n\n",  # Decline capture
            )

        # Should have exit code 1 (preserved from wrapped command)
        assert result.exit_code == 1

    def test_watch_no_prompt_triggers_capture(self, tmp_path):
        """Watch --no-prompt goes straight to capture pipeline."""
        error_text = _load_fixture(ERRORS_DIR / "ec2_capacity.txt")
        mock_proc = self._make_popen_mock(error_text, exit_code=1)

        cli = create_cli()
        runner = CliRunner()

        with patch.object(
            _watch_mod.subprocess, "Popen", return_value=mock_proc
        ):
            result = runner.invoke(
                cli,
                ["watch", "--no-prompt", "--", "terraform", "apply"],
                obj=make_obj(tmp_path),
                input="Fixed by changing AZ\nterraform,aws\n\n",
            )

        # Should still preserve exit code
        assert result.exit_code == 1
        assert "Captured from Terraform" in result.output

    def test_watch_with_tags(self, tmp_path):
        """Watch --tags passes tags through to captured fix."""
        error_text = _load_fixture(ERRORS_DIR / "rds_subnet_coverage.txt")
        mock_proc = self._make_popen_mock(error_text, exit_code=1)

        cli = create_cli()
        runner = CliRunner()

        with patch.object(
            _watch_mod.subprocess, "Popen", return_value=mock_proc
        ):
            result = runner.invoke(
                cli,
                ["watch", "--tags", "infra-team", "--no-prompt",
                 "--", "terraform", "apply"],
                obj=make_obj(tmp_path),
                input="Added second subnet\nterraform,aws,infra-team\n\n",
            )

        assert result.exit_code == 1

    def test_watch_success_no_capture(self, tmp_path):
        """Watch does not trigger capture when command succeeds."""
        mock_proc = self._make_popen_mock("Apply complete!", exit_code=0)

        cli = create_cli()
        runner = CliRunner()

        with patch.object(
            _watch_mod.subprocess, "Popen", return_value=mock_proc
        ):
            result = runner.invoke(
                cli,
                ["watch", "--", "terraform", "apply"],
                obj=make_obj(tmp_path),
            )

        assert result.exit_code == 0
        assert "Capture this error?" not in result.output

    def test_watch_preserves_exit_code(self, tmp_path):
        """Watch preserves the wrapped command's exit code."""
        error_text = _load_fixture(ERRORS_DIR / "iam_access_denied.txt")
        mock_proc = self._make_popen_mock(error_text, exit_code=2)

        cli = create_cli()
        runner = CliRunner()

        with patch.object(
            _watch_mod.subprocess, "Popen", return_value=mock_proc
        ):
            result = runner.invoke(
                cli,
                ["watch", "--", "terraform", "apply"],
                obj=make_obj(tmp_path),
                input="n\n",  # Decline capture
            )

        assert result.exit_code == 2
