"""Tests for the fixdoc demo command."""

import pytest
from click.testing import CliRunner

from fixdoc.models import Fix
from fixdoc.storage import FixRepository
from fixdoc.demo_data import (
    DEMO_TAG,
    TERRAFORM_AWS_ERROR,
    KUBERNETES_CRASHLOOP_ERROR,
    get_seed_fixes,
)
from fixdoc.parsers import detect_and_parse, detect_error_source, ErrorSource
import sys

from fixdoc.commands.demo import demo

# Get the actual module object (not the Click group exported by __init__)
_demo_mod = sys.modules["fixdoc.commands.demo"]


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository for testing."""
    return FixRepository(base_path=tmp_path / ".fixdoc")


@pytest.fixture
def runner():
    return CliRunner()


class TestSeedFixes:
    def test_get_seed_fixes_returns_six(self):
        fixes = get_seed_fixes()
        assert len(fixes) == 6

    def test_all_seed_fixes_have_demo_tag(self):
        for fix in get_seed_fixes():
            tags = [t.strip() for t in fix.tags.split(",")]
            assert DEMO_TAG in tags, f"Fix missing demo tag: {fix.issue[:40]}"

    def test_all_seed_fixes_have_required_fields(self):
        for fix in get_seed_fixes():
            assert fix.issue
            assert fix.resolution
            assert fix.tags
            assert fix.error_excerpt

    def test_seed_saves_to_repo(self, temp_repo):
        fixes = get_seed_fixes()
        for fix in fixes:
            temp_repo.save(fix)
        assert temp_repo.count() == 6

    def test_seed_fixes_are_searchable(self, temp_repo):
        for fix in get_seed_fixes():
            temp_repo.save(fix)

        results = temp_repo.search("S3")
        assert len(results) >= 1

        results = temp_repo.search("CrashLoopBackOff")
        assert len(results) >= 1

        results = temp_repo.search("Helm")
        assert len(results) >= 1


class TestCleanDemoFixes:
    def test_clean_removes_demo_fixes(self, temp_repo):
        # Seed demo fixes
        for fix in get_seed_fixes():
            temp_repo.save(fix)

        # Add a non-demo fix
        non_demo = Fix(issue="Real issue", resolution="Real fix", tags="production")
        temp_repo.save(non_demo)

        assert temp_repo.count() == 7

        # Remove demo fixes
        all_fixes = temp_repo.list_all()
        for fix in all_fixes:
            if fix.tags and DEMO_TAG in [t.strip() for t in fix.tags.split(",")]:
                temp_repo.delete(fix.id)

        assert temp_repo.count() == 1
        remaining = temp_repo.list_all()
        assert remaining[0].issue == "Real issue"


class TestSampleErrorsParseable:
    def test_terraform_error_detected_as_terraform(self):
        source = detect_error_source(TERRAFORM_AWS_ERROR)
        assert source == ErrorSource.TERRAFORM

    def test_terraform_error_parses(self):
        errors = detect_and_parse(TERRAFORM_AWS_ERROR)
        assert len(errors) >= 1
        err = errors[0]
        assert err.error_type == "terraform"

    def test_kubernetes_error_detected_as_kubernetes(self):
        source = detect_error_source(KUBERNETES_CRASHLOOP_ERROR)
        assert source == ErrorSource.KUBERNETES

    def test_kubernetes_error_parses(self):
        errors = detect_and_parse(KUBERNETES_CRASHLOOP_ERROR)
        assert len(errors) >= 1


class TestDemoSeedCommand:
    def test_seed_command(self, runner, tmp_path):
        base_path = tmp_path / ".fixdoc"
        from fixdoc.config import FixDocConfig

        obj = {"base_path": base_path, "config": FixDocConfig()}
        result = runner.invoke(demo, ["seed"], obj=obj)
        assert result.exit_code == 0
        assert "Seeded 6 demo fixes" in result.output
        repo = FixRepository(base_path=base_path)
        assert repo.count() == 6

    def test_seed_clean_flag(self, runner, tmp_path):
        base_path = tmp_path / ".fixdoc"
        from fixdoc.config import FixDocConfig

        obj = {"base_path": base_path, "config": FixDocConfig()}

        # Seed once
        runner.invoke(demo, ["seed"], obj=obj)
        repo = FixRepository(base_path=base_path)
        assert repo.count() == 6

        # Seed again with --clean
        result = runner.invoke(demo, ["seed", "--clean"], obj=obj)
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert repo.count() == 6  # old removed, new added
