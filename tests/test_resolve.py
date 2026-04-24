"""Tests for the fixdoc resolve command."""

import importlib
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig
from fixdoc.pending import PendingEntry

_resolve_mod = importlib.import_module("fixdoc.commands.resolve")


def make_obj(tmp_path):
    return {
        "base_path": tmp_path,
        "config": FixDocConfig(),
        "config_manager": MagicMock(),
    }


def _make_entry(error_id, cwd="/current/dir", **kwargs):
    defaults = dict(
        error_type="terraform",
        short_message="Error: access denied",
        error_excerpt="full error text",
        tags="aws,terraform",
        command="terraform apply",
    )
    defaults.update(kwargs)
    return PendingEntry(error_id=error_id, cwd=cwd, **defaults)


class TestResolveCommand:
    """Tests for the resolve CLI command."""

    def test_no_entries_anywhere_prints_message(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_resolve_mod, "PendingStore") as MockStore:
            instance = MockStore.return_value
            instance.find_by_cwd.return_value = []
            instance.list_all.return_value = []

            result = runner.invoke(cli, ["resolve"], obj=make_obj(tmp_path))

        assert "No pending errors to resolve" in result.output
        assert result.exit_code == 0

    def test_entries_in_other_dirs_shows_count(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()
        other_entries = [_make_entry("id1", cwd="/other/dir")]

        with patch.object(_resolve_mod, "PendingStore") as MockStore:
            instance = MockStore.return_value
            instance.find_by_cwd.return_value = []
            instance.list_all.return_value = other_entries

            result = runner.invoke(cli, ["resolve"], obj=make_obj(tmp_path))

        assert "1 pending in other directories" in result.output
        assert result.exit_code == 0

    def test_matching_entries_calls_resolve_pending_entries(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()
        entry = _make_entry("id1")

        with patch.object(_resolve_mod, "PendingStore") as MockStore, \
             patch.object(_resolve_mod, "resolve_pending_entries") as mock_resolve:
            instance = MockStore.return_value
            instance.find_by_cwd.return_value = [entry]
            mock_resolve.return_value = None

            result = runner.invoke(cli, ["resolve"], obj=make_obj(tmp_path))

        mock_resolve.assert_called_once()
        args = mock_resolve.call_args[0]
        assert args[0] == [entry]  # entries list

    def test_multiple_matching_entries_all_passed(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()
        entries = [_make_entry(f"id{i}") for i in range(3)]

        with patch.object(_resolve_mod, "PendingStore") as MockStore, \
             patch.object(_resolve_mod, "resolve_pending_entries") as mock_resolve:
            instance = MockStore.return_value
            instance.find_by_cwd.return_value = entries
            mock_resolve.return_value = None

            result = runner.invoke(cli, ["resolve"], obj=make_obj(tmp_path))

        args = mock_resolve.call_args[0]
        assert len(args[0]) == 3

    def test_resolve_exits_zero(self, tmp_path):
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_resolve_mod, "PendingStore") as MockStore:
            instance = MockStore.return_value
            instance.find_by_cwd.return_value = []
            instance.list_all.return_value = []

            result = runner.invoke(cli, ["resolve"], obj=make_obj(tmp_path))

        assert result.exit_code == 0


class TestResolvePendingEntries:
    """Tests for resolve_pending_entries() shared flow."""

    def _make_fix(self):
        from fixdoc.models import Fix
        return Fix(issue="something broke", resolution="fixed it", tags="")

    def test_shows_entry_count_header(self, tmp_path):
        from fixdoc.commands._resolve_flow import resolve_pending_entries
        from fixdoc.storage import FixRepository

        runner = CliRunner()
        repo = FixRepository(tmp_path)
        store = MagicMock()
        entry = _make_entry("id1")

        with patch("fixdoc.commands._resolve_flow.handle_piped_input", return_value=None):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    _make_resolve_command(resolve_pending_entries, [entry], repo, store),
                    input="s\n",
                )

        assert "1 deferred error(s)" in result.output

    def test_skip_does_not_save_fix_but_clears_entry(self, tmp_path):
        from fixdoc.commands._resolve_flow import resolve_pending_entries
        from fixdoc.storage import FixRepository

        runner = CliRunner()
        repo = FixRepository(tmp_path)
        store = MagicMock()
        entry = _make_entry("id1")

        with patch("fixdoc.commands._resolve_flow.handle_piped_input", return_value=None):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    _make_resolve_command(resolve_pending_entries, [entry], repo, store),
                    input="s\n",
                )

        # Clear-on-resolve: skipped entries are cleaned up after the loop
        store.remove.assert_called_once_with("id1")

    def test_quit_stops_iteration_and_clears_remaining(self, tmp_path):
        from fixdoc.commands._resolve_flow import resolve_pending_entries
        from fixdoc.storage import FixRepository

        runner = CliRunner()
        repo = FixRepository(tmp_path)
        store = MagicMock()
        entries = [_make_entry(f"id{i}") for i in range(3)]

        with patch("fixdoc.commands._resolve_flow.handle_piped_input", return_value=None):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    _make_resolve_command(resolve_pending_entries, entries, repo, store),
                    input="q\n",
                )

        # Clear-on-resolve: all 3 entries cleaned up (none were captured)
        assert store.remove.call_count == 3

    def test_capture_saves_and_removes_entry(self, tmp_path):
        from fixdoc.commands._resolve_flow import resolve_pending_entries
        from fixdoc.storage import FixRepository
        from fixdoc.models import Fix

        runner = CliRunner()
        repo = FixRepository(tmp_path)
        store = MagicMock()
        entry = _make_entry("id1")
        mock_fix = Fix(issue="broke", resolution="fixed", tags="")

        with patch("fixdoc.commands._resolve_flow.handle_piped_input", return_value=mock_fix):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    _make_resolve_command(resolve_pending_entries, [entry], repo, store),
                    input="\n",
                )

        store.remove.assert_called_once_with("id1")
        assert "Fix saved" in result.output


class TestGroupByError:
    """Tests for _group_by_error bundling logic."""

    def test_identical_error_code_and_message_bundled(self):
        from fixdoc.commands._resolve_flow import _group_by_error

        e1 = _make_entry("id1", error_code="InvalidInstanceType",
                         short_message="InvalidInstanceType: grgr")
        e2 = _make_entry("id2", error_code="InvalidInstanceType",
                         short_message="InvalidInstanceType: grgr")

        groups = _group_by_error([e1, e2])
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_different_error_codes_not_bundled(self):
        from fixdoc.commands._resolve_flow import _group_by_error

        e1 = _make_entry("id1", error_code="AccessDenied",
                         short_message="AccessDenied: access denied")
        e2 = _make_entry("id2", error_code="InvalidInstanceType",
                         short_message="InvalidInstanceType: bad type")

        groups = _group_by_error([e1, e2])
        assert len(groups) == 2

    def test_uuid_normalized_for_grouping(self):
        from fixdoc.commands._resolve_flow import _group_by_error

        msg1 = "TimeoutError: request 123e4567-e89b-12d3-a456-426614174000 timed out"
        msg2 = "TimeoutError: request 99999999-0000-1111-2222-333333333333 timed out"
        e1 = _make_entry("id1", error_code="TimeoutError", short_message=msg1)
        e2 = _make_entry("id2", error_code="TimeoutError", short_message=msg2)

        groups = _group_by_error([e1, e2])
        assert len(groups) == 1

    def test_no_error_code_each_is_own_group(self):
        from fixdoc.commands._resolve_flow import _group_by_error

        e1 = _make_entry("id1", error_code=None, short_message="some error")
        e2 = _make_entry("id2", error_code=None, short_message="some error")

        groups = _group_by_error([e1, e2])
        assert len(groups) == 2

    def test_bundle_prompt_shows_plus_n_more(self, tmp_path):
        from fixdoc.commands._resolve_flow import resolve_pending_entries
        from fixdoc.storage import FixRepository

        runner = CliRunner()
        repo = FixRepository(tmp_path)
        store = MagicMock()
        e1 = _make_entry("id1", error_code="InvalidType",
                         short_message="InvalidType: bad val",
                         resource_address="module.app_a.aws_instance.app")
        e2 = _make_entry("id2", error_code="InvalidType",
                         short_message="InvalidType: bad val",
                         resource_address="module.app_b.aws_instance.app")

        with patch("fixdoc.commands._resolve_flow.handle_piped_input", return_value=None):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    _make_resolve_command(resolve_pending_entries, [e1, e2], repo, store),
                    input="s\n",
                )

        assert "+ 1 more" in result.output

    def test_capture_bundle_removes_all_group_entries(self, tmp_path):
        from fixdoc.commands._resolve_flow import resolve_pending_entries
        from fixdoc.storage import FixRepository
        from fixdoc.models import Fix

        runner = CliRunner()
        repo = FixRepository(tmp_path)
        store = MagicMock()
        e1 = _make_entry("id1", error_code="InvalidType",
                         short_message="InvalidType: bad val")
        e2 = _make_entry("id2", error_code="InvalidType",
                         short_message="InvalidType: bad val")
        mock_fix = Fix(issue="broke", resolution="fixed", tags="")

        with patch("fixdoc.commands._resolve_flow.handle_piped_input", return_value=mock_fix):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    _make_resolve_command(resolve_pending_entries, [e1, e2], repo, store),
                    input="\n",
                )

        removed_ids = {call.args[0] for call in store.remove.call_args_list}
        assert "id1" in removed_ids
        assert "id2" in removed_ids


def _make_resolve_command(resolve_fn, entries, repo, store):
    """Wrap resolve_pending_entries in a Click command for testing."""
    import click

    @click.command()
    def cmd():
        resolve_fn(entries, repo, FixDocConfig(), store)

    return cmd
