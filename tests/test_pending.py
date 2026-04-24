"""Tests for the pending error storage and CLI command."""

import importlib
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig
from fixdoc.parsers.base import ParsedError, CloudProvider
from fixdoc.pending import (
    PendingEntry,
    PendingStore,
    pending_entry_from_parsed_error,
)

_pending_cmd_mod = importlib.import_module("fixdoc.commands.pending")


def make_obj(tmp_path):
    """Create a ctx.obj dict for test invocations."""
    return {
        "base_path": tmp_path,
        "config": FixDocConfig(),
        "config_manager": MagicMock(),
    }


def _make_parsed_error(**kwargs):
    """Create a minimal ParsedError for testing."""
    defaults = dict(
        error_type="terraform",
        error_message="AccessDenied: access denied",
        raw_output="Error: AccessDenied on aws_iam_role.app",
        resource_address="aws_iam_role.app",
        error_code="AccessDenied",
    )
    defaults.update(kwargs)
    return ParsedError(**defaults)


# ===================================================================
# PendingEntry
# ===================================================================


class TestPendingEntry:
    """Tests for PendingEntry dataclass."""

    def test_to_dict_roundtrip(self):
        entry = PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="access denied",
            error_excerpt="Error: access denied",
            tags="aws,terraform",
            resource_address="aws_iam_role.app",
            error_code="AccessDenied",
        )
        d = entry.to_dict()
        restored = PendingEntry.from_dict(d)
        assert restored.error_id == "abc123"
        assert restored.error_type == "terraform"
        assert restored.resource_address == "aws_iam_role.app"
        assert restored.error_code == "AccessDenied"
        assert restored.tags == "aws,terraform"

    def test_from_dict_missing_optional_fields(self):
        d = {
            "error_id": "abc123",
            "error_type": "terraform",
            "short_message": "error",
            "error_excerpt": "Error: something",
        }
        entry = PendingEntry.from_dict(d)
        assert entry.resource_address is None
        assert entry.error_code is None
        assert entry.file is None
        assert entry.command is None
        assert entry.tags == ""

    def test_deferred_at_auto_populated(self):
        entry = PendingEntry(
            error_id="x",
            error_type="terraform",
            short_message="err",
            error_excerpt="err",
            tags="",
        )
        assert entry.deferred_at != ""
        assert "T" in entry.deferred_at  # ISO format


# ===================================================================
# pending_entry_from_parsed_error
# ===================================================================


class TestPendingEntryFromParsedError:
    """Tests for the helper function."""

    def test_creates_entry_from_parsed_error(self):
        err = _make_parsed_error()
        entry = pending_entry_from_parsed_error(err, command="terraform apply")
        assert entry.error_id == err.error_id
        assert entry.error_type == "terraform"
        assert entry.resource_address == "aws_iam_role.app"
        assert entry.error_code == "AccessDenied"
        assert entry.command == "terraform apply"
        assert len(entry.short_message) <= 120

    def test_truncates_excerpt_to_2000(self):
        err = _make_parsed_error(raw_output="x" * 5000)
        entry = pending_entry_from_parsed_error(err)
        assert len(entry.error_excerpt) == 2000

    def test_file_line_combined(self):
        err = _make_parsed_error(file="main.tf", line=42)
        entry = pending_entry_from_parsed_error(err)
        assert entry.file == "main.tf:42"

    def test_file_without_line(self):
        err = _make_parsed_error(file="main.tf", line=None)
        entry = pending_entry_from_parsed_error(err)
        assert entry.file == "main.tf"

    def test_no_command(self):
        err = _make_parsed_error()
        entry = pending_entry_from_parsed_error(err)
        assert entry.command is None


# ===================================================================
# PendingStore
# ===================================================================


class TestPendingStore:
    """Tests for PendingStore CRUD operations."""

    def test_empty_store_list_all(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.list_all() == []

    def test_save_and_list(self, tmp_path):
        store = PendingStore(tmp_path)
        entry = PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error: something",
            tags="aws",
        )
        store.save(entry)
        entries = store.list_all()
        assert len(entries) == 1
        assert entries[0].error_id == "abc123"

    def test_save_replaces_same_error_id(self, tmp_path):
        store = PendingStore(tmp_path)
        entry1 = PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error v1",
            error_excerpt="Error v1",
            tags="aws",
        )
        entry2 = PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error v2",
            error_excerpt="Error v2",
            tags="aws",
        )
        store.save(entry1)
        store.save(entry2)
        entries = store.list_all()
        assert len(entries) == 1
        assert entries[0].short_message == "error v2"

    def test_save_multiple_different_ids(self, tmp_path):
        store = PendingStore(tmp_path)
        for i in range(3):
            store.save(PendingEntry(
                error_id=f"id{i}",
                error_type="terraform",
                short_message=f"error {i}",
                error_excerpt=f"Error {i}",
                tags="",
            ))
        assert len(store.list_all()) == 3

    def test_remove_by_exact_id(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
        ))
        assert store.remove("abc123") is True
        assert store.list_all() == []

    def test_remove_by_prefix(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(PendingEntry(
            error_id="abc123def456",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
        ))
        assert store.remove("abc123") is True
        assert store.list_all() == []

    def test_remove_nonexistent_returns_false(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.remove("nonexistent") is False

    def test_clear_returns_count(self, tmp_path):
        store = PendingStore(tmp_path)
        for i in range(3):
            store.save(PendingEntry(
                error_id=f"id{i}",
                error_type="terraform",
                short_message=f"error {i}",
                error_excerpt=f"Error {i}",
                tags="",
            ))
        assert store.clear() == 3
        assert store.list_all() == []

    def test_clear_empty_returns_zero(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.clear() == 0

    def test_get_by_exact_id(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
        ))
        entry = store.get("abc123")
        assert entry is not None
        assert entry.error_id == "abc123"

    def test_get_by_prefix(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(PendingEntry(
            error_id="abc123def456",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
        ))
        entry = store.get("abc123")
        assert entry is not None

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.get("nonexistent") is None

    def test_pending_file_location(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.path == tmp_path / ".fixdoc-pending"

    def test_corrupted_json_returns_empty(self, tmp_path):
        store = PendingStore(tmp_path)
        store.path.write_text("not valid json", encoding="utf-8")
        assert store.list_all() == []

    def test_non_list_json_returns_empty(self, tmp_path):
        store = PendingStore(tmp_path)
        store.path.write_text('{"key": "value"}', encoding="utf-8")
        assert store.list_all() == []

    def test_supersede_context_marks_matching_entries(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(PendingEntry(
            error_id="id1",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
            command="terraform apply",
            cwd="/my/project",
            command_family="terraform apply",
        ))
        store.save(PendingEntry(
            error_id="id2",
            error_type="terraform",
            short_message="other error",
            error_excerpt="Other Error",
            tags="",
            command="terraform apply --auto-approve",
            cwd="/my/project",
            command_family="terraform apply",
        ))
        # Different cwd — should NOT be superseded
        store.save(PendingEntry(
            error_id="id3",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
            command="terraform apply",
            cwd="/other/project",
            command_family="terraform apply",
        ))
        count = store.supersede_context("/my/project", "terraform apply")
        assert count == 2
        # All 3 entries still exist (superseded ones are NOT deleted)
        all_entries = store.list_all(include_superseded=True)
        assert len(all_entries) == 3
        # Only id3 remains as "pending"
        pending = store.list_all()
        assert len(pending) == 1
        assert pending[0].error_id == "id3"

    def test_supersede_context_returns_zero_when_no_match(self, tmp_path):
        store = PendingStore(tmp_path)
        store.save(PendingEntry(
            error_id="id1",
            error_type="terraform",
            short_message="error",
            error_excerpt="Error",
            tags="",
            command="terraform apply",
            cwd="/other/project",
            command_family="terraform apply",
        ))
        count = store.supersede_context("/my/project", "terraform apply")
        assert count == 0
        assert len(store.list_all()) == 1

    def test_supersede_context_empty_store_returns_zero(self, tmp_path):
        store = PendingStore(tmp_path)
        assert store.supersede_context("/my/project", "terraform apply") == 0


# ===================================================================
# PendingStore git root detection
# ===================================================================


class TestPendingStoreGitRoot:
    """Tests for git root detection in PendingStore."""

    def test_uses_git_root_when_available(self, tmp_path):
        """When git rev-parse succeeds, uses that directory."""
        git_root = tmp_path / "repo"
        git_root.mkdir()

        with patch("fixdoc.pending.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=str(git_root) + "\n"
            )
            store = PendingStore(tmp_path)

        assert store.path == git_root / ".fixdoc-pending"

    def test_falls_back_to_project_dir(self, tmp_path):
        """When git rev-parse fails, uses the provided directory."""
        with patch("fixdoc.pending.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            store = PendingStore(tmp_path)

        assert store.path == tmp_path / ".fixdoc-pending"

    def test_falls_back_when_git_not_found(self, tmp_path):
        """When git is not installed, uses the provided directory."""
        with patch("fixdoc.pending.subprocess.run", side_effect=FileNotFoundError):
            store = PendingStore(tmp_path)

        assert store.path == tmp_path / ".fixdoc-pending"


# ===================================================================
# CLI: fixdoc pending (list)
# ===================================================================


class TestPendingListCommand:
    """Tests for 'fixdoc pending' (list subcommand)."""

    def test_empty_pending_list(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            MockStore.return_value.list_all.return_value = []
            result = runner.invoke(cli, ["pending"], obj=make_obj(tmp_path))

        assert "No pending errors" in result.output
        assert result.exit_code == 0

    def test_lists_pending_entries(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        entries = [
            PendingEntry(
                error_id="abc123def456",
                error_type="terraform",
                short_message="access denied",
                error_excerpt="Error",
                tags="aws",
                resource_address="aws_iam_role.app",
                error_code="AccessDenied",
                deferred_at="2026-02-17T10:00:00",
            ),
        ]

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            MockStore.return_value.list_all.return_value = entries
            result = runner.invoke(cli, ["pending"], obj=make_obj(tmp_path))

        assert "abc123def456" in result.output
        assert "aws_iam_role.app" in result.output
        assert "AccessDenied" in result.output
        assert "1 pending error(s)" in result.output
        assert result.exit_code == 0


# ===================================================================
# CLI: fixdoc pending clear
# ===================================================================


class TestPendingClearCommand:
    """Tests for 'fixdoc pending clear'."""

    def test_clear_with_entries(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            MockStore.return_value.clear.return_value = 3
            result = runner.invoke(cli, ["pending", "clear"], obj=make_obj(tmp_path))

        assert "Cleared 3 pending error(s)" in result.output
        assert result.exit_code == 0

    def test_clear_empty(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            MockStore.return_value.clear.return_value = 0
            result = runner.invoke(cli, ["pending", "clear"], obj=make_obj(tmp_path))

        assert "No pending errors to clear" in result.output
        assert result.exit_code == 0


# ===================================================================
# CLI: fixdoc pending remove
# ===================================================================


class TestPendingRemoveCommand:
    """Tests for 'fixdoc pending remove'."""

    def test_remove_by_id(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        entry = PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error msg",
            error_excerpt="Error",
            tags="",
        )

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            store_instance = MockStore.return_value
            store_instance.list_all.return_value = [entry]
            store_instance.get.return_value = entry
            store_instance.remove.return_value = True

            result = runner.invoke(
                cli, ["pending", "remove", "abc123"], obj=make_obj(tmp_path)
            )

        assert "Removed:" in result.output
        assert result.exit_code == 0

    def test_remove_by_number(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        entry = PendingEntry(
            error_id="abc123",
            error_type="terraform",
            short_message="error msg",
            error_excerpt="Error",
            tags="",
        )

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            store_instance = MockStore.return_value
            store_instance.list_all.return_value = [entry]
            store_instance.get.return_value = None
            store_instance.remove.return_value = True

            result = runner.invoke(
                cli, ["pending", "remove", "1"], obj=make_obj(tmp_path)
            )

        assert "Removed:" in result.output
        assert result.exit_code == 0

    def test_remove_nonexistent(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            store_instance = MockStore.return_value
            store_instance.list_all.return_value = []
            store_instance.get.return_value = None

            result = runner.invoke(
                cli, ["pending", "remove", "nonexistent"], obj=make_obj(tmp_path)
            )

        assert "No pending error matching" in result.output


# ===================================================================
# CLI: fixdoc pending capture
# ===================================================================


class TestPendingCaptureCommand:
    """Tests for 'fixdoc pending capture'."""

    def test_capture_nonexistent_entry(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_pending_cmd_mod, "PendingStore") as MockStore:
            store_instance = MockStore.return_value
            store_instance.list_all.return_value = []
            store_instance.get.return_value = None

            result = runner.invoke(
                cli, ["pending", "capture", "nonexistent"], obj=make_obj(tmp_path)
            )

        assert "No pending error matching" in result.output


# ===================================================================
# compute_error_id
# ===================================================================


class TestComputeErrorId:
    """Tests for the error_id computation."""

    def test_stable_hash(self):
        err1 = _make_parsed_error()
        err2 = _make_parsed_error()
        assert err1.error_id == err2.error_id
        assert len(err1.error_id) == 12

    def test_different_resource_different_id(self):
        err1 = _make_parsed_error(resource_address="aws_iam_role.a")
        err2 = _make_parsed_error(resource_address="aws_iam_role.b")
        assert err1.error_id != err2.error_id

    def test_different_error_code_different_id(self):
        err1 = _make_parsed_error(error_code="AccessDenied")
        err2 = _make_parsed_error(error_code="NotFound")
        assert err1.error_id != err2.error_id

    def test_all_empty_still_produces_id(self):
        err = ParsedError(
            error_type="generic",
            error_message="",
            raw_output="",
        )
        assert len(err.error_id) == 12
