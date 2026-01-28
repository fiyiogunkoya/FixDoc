"""Tests for sync engine."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from fixdoc.models import Fix
from fixdoc.storage import FixRepository
from fixdoc.config import ConfigManager, FixDocConfig, SyncConfig, UserConfig
from fixdoc.git import GitOperations, SyncStatus, GitStatusInfo
from fixdoc.sync_engine import SyncEngine, SyncResult, SyncConflict, ConflictType


@pytest.fixture
def temp_fixdoc(tmp_path):
    """Create a temporary fixdoc directory with repo."""
    fixdoc_path = tmp_path / ".fixdoc"
    fixdoc_path.mkdir()
    (fixdoc_path / "docs").mkdir()
    return fixdoc_path


@pytest.fixture
def repo(temp_fixdoc):
    """Create a FixRepository."""
    return FixRepository(temp_fixdoc)


@pytest.fixture
def config_manager(temp_fixdoc):
    """Create a ConfigManager with sync configured."""
    manager = ConfigManager(temp_fixdoc)
    config = FixDocConfig(
        sync=SyncConfig(
            remote_url="git@github.com:test/repo.git",
            branch="main",
        ),
        user=UserConfig(name="Test User", email="test@example.com"),
    )
    manager.save(config)
    return manager


@pytest.fixture
def mock_git(temp_fixdoc):
    """Create a mocked GitOperations."""
    git = Mock(spec=GitOperations)
    git.repo_path = temp_fixdoc
    git.has_uncommitted_changes.return_value = True
    git.has_remote.return_value = True
    return git


class TestSyncEnginePrepare:
    def test_prepare_push_returns_all_non_private(self, repo, config_manager, mock_git):
        fix1 = Fix(issue="Issue 1", resolution="Resolution 1")
        fix2 = Fix(issue="Issue 2", resolution="Resolution 2")
        fix3 = Fix(issue="Issue 3", resolution="Resolution 3", is_private=True)
        repo.save(fix1)
        repo.save(fix2)
        repo.save(fix3)

        engine = SyncEngine(repo, mock_git, config_manager)
        pushable = engine.prepare_push()

        assert len(pushable) == 2
        ids = [f.id for f in pushable]
        assert fix1.id in ids
        assert fix2.id in ids
        assert fix3.id not in ids

    def test_prepare_push_excludes_config_private(self, repo, config_manager, mock_git):
        fix1 = Fix(issue="Issue 1", resolution="Resolution 1")
        fix2 = Fix(issue="Issue 2", resolution="Resolution 2")
        repo.save(fix1)
        repo.save(fix2)

        config_manager.add_private_fix(fix1.id)

        engine = SyncEngine(repo, mock_git, config_manager)
        pushable = engine.prepare_push()

        assert len(pushable) == 1
        assert pushable[0].id == fix2.id


class TestSyncEnginePush:
    def test_push_without_config_fails(self, repo, temp_fixdoc, mock_git):
        manager = ConfigManager(temp_fixdoc)  # Empty config
        engine = SyncEngine(repo, mock_git, manager)

        result = engine.execute_push([Fix(issue="Test", resolution="Test")])

        assert result.success is False
        assert "not configured" in result.error_message.lower()

    def test_push_empty_list_succeeds(self, repo, config_manager, mock_git):
        engine = SyncEngine(repo, mock_git, config_manager)

        result = engine.execute_push([])

        assert result.success is True
        assert result.pushed_fixes == []

    def test_push_sets_author_from_config(self, repo, config_manager, mock_git):
        fix = Fix(issue="Test Issue", resolution="Test Resolution")
        repo.save(fix)

        engine = SyncEngine(repo, mock_git, config_manager)
        engine.execute_push([fix])

        # Reload the fix to check author was set
        updated = repo.get(fix.id)
        assert updated.author == "Test User"
        assert updated.author_email == "test@example.com"

    def test_push_calls_git_operations(self, repo, config_manager, mock_git):
        fix = Fix(issue="Test Issue", resolution="Test Resolution")
        repo.save(fix)

        mock_git.commit.return_value = "abc123"

        engine = SyncEngine(repo, mock_git, config_manager)
        result = engine.execute_push([fix], commit_message="Test commit")

        mock_git.add.assert_called_once_with("docs/")
        mock_git.commit.assert_called_once()
        mock_git.push.assert_called_once_with(branch="main")
        assert result.success is True


class TestSyncEnginePull:
    def test_pull_without_config_fails(self, repo, temp_fixdoc, mock_git):
        manager = ConfigManager(temp_fixdoc)  # Empty config
        engine = SyncEngine(repo, mock_git, manager)

        result = engine.execute_pull()

        assert result.success is False
        assert "not configured" in result.error_message.lower()

    def test_pull_success_rebuilds_from_markdown(self, repo, config_manager, mock_git):
        mock_git.pull.return_value = (False, [])

        # Create a markdown file to simulate remote fix
        docs_path = repo.docs_path
        fix_id = "remote-fix-uuid"
        md_content = """# Fix: remote-f

**Created:** 2024-01-15T10:30:00+00:00
**Updated:** 2024-01-15T10:30:00+00:00

## Issue

Remote issue from teammate

## Resolution

Remote resolution
"""
        (docs_path / f"{fix_id}.md").write_text(md_content)

        engine = SyncEngine(repo, mock_git, config_manager)
        result = engine.execute_pull()

        assert result.success is True
        assert fix_id in result.pulled_fixes

        # Verify fix was added to database
        pulled = repo.get(fix_id)
        assert pulled is not None
        assert pulled.issue == "Remote issue from teammate"

    def test_pull_with_conflicts_returns_conflicts(self, repo, config_manager, mock_git):
        mock_git.pull.return_value = (True, ["docs/conflict-fix.md"])
        mock_git.reset_hard = Mock()

        engine = SyncEngine(repo, mock_git, config_manager)
        result = engine.execute_pull()

        assert result.success is False
        assert len(result.conflicts) == 1
        assert result.conflicts[0].fix_id == "conflict-fix"

    def test_pull_force_stashes_and_pops(self, repo, config_manager, mock_git):
        mock_git.has_uncommitted_changes.return_value = True
        mock_git.pull.return_value = (False, [])
        mock_git.stash.return_value = True

        engine = SyncEngine(repo, mock_git, config_manager)
        result = engine.execute_pull(force=True)

        mock_git.stash.assert_called_once()
        mock_git.stash_pop.assert_called_once()


class TestSyncEngineConflictResolution:
    def test_resolve_conflict_local(self, repo, config_manager, mock_git):
        local_fix = Fix(
            id="conflict-id",
            issue="Local issue",
            resolution="Local resolution",
        )
        conflict = SyncConflict(
            fix_id="conflict-id",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_fix=local_fix,
            remote_fix=None,
        )

        engine = SyncEngine(repo, mock_git, config_manager)
        resolved = engine.resolve_conflict(conflict, "local")

        assert resolved == local_fix

    def test_resolve_conflict_remote(self, repo, config_manager, mock_git):
        remote_fix = Fix(
            id="conflict-id",
            issue="Remote issue",
            resolution="Remote resolution",
        )
        conflict = SyncConflict(
            fix_id="conflict-id",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_fix=None,
            remote_fix=remote_fix,
        )

        engine = SyncEngine(repo, mock_git, config_manager)
        resolved = engine.resolve_conflict(conflict, "remote")

        assert resolved == remote_fix

    def test_resolve_conflict_merge(self, repo, config_manager, mock_git):
        local_fix = Fix(
            id="conflict-id",
            issue="Local issue",
            resolution="Local resolution",
            tags="local-tag",
            notes="Local notes",
            created_at="2024-01-15T10:00:00+00:00",
            updated_at="2024-01-15T10:00:00+00:00",
        )
        remote_fix = Fix(
            id="conflict-id",
            issue="Remote issue",
            resolution="Remote resolution",
            tags="remote-tag",
            notes="Remote notes",
            created_at="2024-01-15T10:00:00+00:00",
            updated_at="2024-01-16T10:00:00+00:00",
        )
        conflict = SyncConflict(
            fix_id="conflict-id",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_fix=local_fix,
            remote_fix=remote_fix,
        )

        engine = SyncEngine(repo, mock_git, config_manager)
        resolved = engine.resolve_conflict(conflict, "merge")

        assert resolved is not None
        assert resolved.id == "conflict-id"
        # Remote issue takes precedence
        assert resolved.issue == "Remote issue"
        # Tags should be merged
        assert "local-tag" in resolved.tags
        assert "remote-tag" in resolved.tags
        # Notes should contain both
        assert "Local" in resolved.notes
        assert "Remote" in resolved.notes


class TestSyncEngineStatus:
    def test_status_not_configured(self, repo, temp_fixdoc, mock_git):
        manager = ConfigManager(temp_fixdoc)  # Empty config
        engine = SyncEngine(repo, mock_git, manager)

        status = engine.get_sync_status()

        assert status["configured"] is False

    def test_status_with_config(self, repo, config_manager, mock_git):
        mock_git.get_status.return_value = GitStatusInfo(
            status=SyncStatus.AHEAD,
            commits_ahead=2,
            commits_behind=0,
            local_changes=["docs/fix1.md"],
        )

        fix = Fix(issue="Test", resolution="Test")
        repo.save(fix)

        engine = SyncEngine(repo, mock_git, config_manager)
        status = engine.get_sync_status()

        assert status["configured"] is True
        assert status["remote_url"] == "git@github.com:test/repo.git"
        assert status["status"] == "ahead"
        assert status["commits_ahead"] == 2
        assert status["total_fixes"] == 1
