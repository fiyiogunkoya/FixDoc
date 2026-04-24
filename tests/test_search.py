"""Tests for fixdoc search command and multi-word matching."""

import os
import pytest
from unittest.mock import MagicMock

from click.testing import CliRunner

from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig
from fixdoc.models import Fix
from fixdoc.storage import FixRepository


def make_obj(tmp_path):
    """Create a ctx.obj dict for test invocations."""
    return {
        "base_path": tmp_path,
        "config": FixDocConfig(),
        "config_manager": MagicMock(),
    }


@pytest.fixture
def seeded_path(tmp_path):
    """Create a path with seeded fixes for CLI tests."""
    repo = FixRepository(tmp_path)
    repo.save(Fix(
        issue="Security group update failed - InvalidGroup.NotFound",
        resolution="Create security group first",
        tags="terraform,aws,aws_security_group,network",
    ))
    repo.save(Fix(
        issue="S3 bucket timeout during creation",
        resolution="Retry with exponential backoff",
        tags="terraform,aws,aws_s3_bucket",
    ))
    repo.save(Fix(
        issue="Kubernetes pod CrashLoopBackOff",
        resolution="Check logs and fix startup",
        tags="kubernetes,pod",
    ))
    repo.save(Fix(
        issue="Azure storage account RBAC denied",
        resolution="Add Contributor role",
        tags="terraform,azure,rbac",
    ))
    return tmp_path


# ===================================================================
# TestMultiWordMatching (models.py)
# ===================================================================


class TestMultiWordMatching:
    def test_and_matching_both_words_present(self):
        fix = Fix(issue="Security group update failed", resolution="Fix it")
        assert fix.matches("security group") is True

    def test_and_matching_one_word_missing(self):
        fix = Fix(issue="Security group update failed", resolution="Fix it")
        assert fix.matches("security bucket") is False

    def test_or_matching_one_word_present(self):
        fix = Fix(issue="Security group update failed", resolution="Fix it")
        assert fix.matches("security bucket", match_any=True) is True

    def test_or_matching_no_words_present(self):
        fix = Fix(issue="Security group update failed", resolution="Fix it")
        assert fix.matches("kubernetes pod", match_any=True) is False

    def test_case_insensitive(self):
        fix = Fix(issue="Security Group Update", resolution="Fix it")
        assert fix.matches("security group") is True

    def test_empty_query(self):
        fix = Fix(issue="Something", resolution="Fix it")
        assert fix.matches("") is False

    def test_searches_all_fields(self):
        fix = Fix(
            issue="Issue here",
            resolution="Resolution here",
            tags="terraform,aws",
            error_excerpt="Error excerpt",
            notes="Some notes",
        )
        assert fix.matches("terraform excerpt") is True


# ===================================================================
# TestMatchesTags (models.py)
# ===================================================================


class TestMatchesTags:
    def test_and_matching_all_present(self):
        fix = Fix(issue="Test", resolution="Fix", tags="terraform,aws,s3")
        assert fix.matches_tags(["terraform", "aws"]) is True

    def test_and_matching_one_missing(self):
        fix = Fix(issue="Test", resolution="Fix", tags="terraform,aws,s3")
        assert fix.matches_tags(["terraform", "azure"]) is False

    def test_or_matching_one_present(self):
        fix = Fix(issue="Test", resolution="Fix", tags="terraform,aws,s3")
        assert fix.matches_tags(["terraform", "azure"], match_any=True) is True

    def test_or_matching_none_present(self):
        fix = Fix(issue="Test", resolution="Fix", tags="terraform,aws,s3")
        assert fix.matches_tags(["kubernetes", "azure"], match_any=True) is False

    def test_case_insensitive(self):
        fix = Fix(issue="Test", resolution="Fix", tags="Terraform,AWS")
        assert fix.matches_tags(["terraform", "aws"]) is True

    def test_no_tags(self):
        fix = Fix(issue="Test", resolution="Fix")
        assert fix.matches_tags(["terraform"]) is False

    def test_empty_required(self):
        fix = Fix(issue="Test", resolution="Fix", tags="terraform")
        assert fix.matches_tags([]) is True


# ===================================================================
# TestSearchCommand (CLI)
# ===================================================================


class TestSearchCommand:
    def _invoke(self, seeded_path, args):
        """Invoke CLI with FIXDOC_HOME pointing to the test path."""
        runner = CliRunner(env={"FIXDOC_HOME": str(seeded_path)})
        cli = create_cli()
        return runner.invoke(cli, args)

    def test_basic_search(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "security group"])

        assert result.exit_code == 0
        assert "1 fix(es)" in result.output
        assert "Security group" in result.output

    def test_search_no_results(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "nonexistent unicorn"])

        assert result.exit_code == 0
        assert "No fixes found" in result.output

    def test_search_with_any_flag(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "security kubernetes", "--any"])

        assert result.exit_code == 0
        # Should match both security group fix and kubernetes fix
        assert "2 fix(es)" in result.output

    def test_search_with_tags_filter(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "terraform", "--tags", "aws"])

        assert result.exit_code == 0
        # Should only match terraform+aws fixes (security group and s3)
        assert "fix(es)" in result.output

    def test_search_with_tags_filter_no_match(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "timeout", "--tags", "kubernetes"])

        assert result.exit_code == 0
        assert "No fixes found" in result.output

    def test_search_with_any_tags(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "terraform", "--tags", "aws,azure", "--any-tags"])

        assert result.exit_code == 0
        # Should match all terraform fixes with aws OR azure tag
        assert "fix(es)" in result.output

    def test_search_limit(self, seeded_path):
        result = self._invoke(seeded_path, ["search", "terraform", "--limit", "1", "--tags", "aws", "--any-tags"])

        assert result.exit_code == 0
