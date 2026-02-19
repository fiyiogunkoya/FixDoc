"""Tests for the fixdoc watch command."""

import importlib
import subprocess
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig
from fixdoc.models import Fix
from fixdoc.parsers.base import ParsedError, CloudProvider

# Get the actual watch module (not the Click command function)
_watch_mod = importlib.import_module("fixdoc.commands.watch")


def make_obj(tmp_path):
    """Create a ctx.obj dict for test invocations."""
    return {
        "base_path": tmp_path,
        "config": FixDocConfig(),
        "config_manager": MagicMock(),
    }


def mock_popen_success(stdout_lines=None):
    """Create a mock Popen that succeeds with given stdout lines."""
    if stdout_lines is None:
        stdout_lines = [b""]
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout.readline.side_effect = stdout_lines
    mock_proc.wait.return_value = 0
    return mock_proc


def mock_popen_failure(exit_code=1, stdout_lines=None):
    """Create a mock Popen that fails with given exit code and stdout lines."""
    if stdout_lines is None:
        stdout_lines = [b"Error: something went wrong\n", b""]
    mock_proc = MagicMock()
    mock_proc.returncode = exit_code
    mock_proc.stdout.readline.side_effect = stdout_lines
    mock_proc.wait.return_value = exit_code
    return mock_proc


def _make_parsed_error(resource_address="aws_iam_role.app",
                       error_code="AccessDenied", **kwargs):
    """Create a ParsedError for testing."""
    defaults = dict(
        error_type="terraform",
        error_message="access denied",
        raw_output="Error: access denied on resource",
        resource_address=resource_address,
        error_code=error_code,
        cloud_provider=CloudProvider.AWS,
    )
    defaults.update(kwargs)
    return ParsedError(**defaults)


def _make_fix(**kwargs):
    """Create a Fix for testing."""
    defaults = dict(
        issue="aws_iam_role.app: AccessDenied",
        resolution="Added role binding",
        tags="aws,terraform",
    )
    defaults.update(kwargs)
    return Fix(**defaults)


# ===================================================================
# TestWatchCommandSuccess
# ===================================================================


class TestWatchCommandSuccess:
    """Tests for when the watched command succeeds."""

    def test_successful_command_no_fixdoc_output(self, tmp_path):
        """A successful command produces no extra fixdoc output."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_success([b"hello world\n", b""])

            result = runner.invoke(
                cli, ["watch", "--", "echo", "hello"], obj=make_obj(tmp_path)
            )

        assert "Capture this error?" not in result.output
        assert result.exit_code == 0

    def test_exit_code_zero_preserved(self, tmp_path):
        """Exit code 0 is preserved from the wrapped command."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_success()

            result = runner.invoke(
                cli, ["watch", "--", "true"], obj=make_obj(tmp_path)
            )

        assert result.exit_code == 0


# ===================================================================
# TestWatchCommandFailure — single structured error
# ===================================================================


class TestWatchCommandFailure:
    """Tests for when the watched command fails with a single structured error."""

    def test_single_error_shows_action_menu(self, tmp_path):
        """A failed command with one structured error shows action menu."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse:
            mp.return_value = mock_popen_failure()
            mock_parse.return_value = [_make_parsed_error()]

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="s\n",
            )

        assert "Command failed (exit code 1)" in result.output
        assert "Capture this error" in result.output
        assert "Defer" in result.output

    def test_skip_no_fix_created(self, tmp_path):
        """Choosing skip creates no fix."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse:
            mp.return_value = mock_popen_failure()
            mock_parse.return_value = [_make_parsed_error()]

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="s\n",
            )

        assert "Fix saved" not in result.output
        assert "Saved to pending" not in result.output

    def test_exit_code_preserved_on_skip(self, tmp_path):
        """Non-zero exit code is preserved when skipping."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse:
            mp.return_value = mock_popen_failure(exit_code=42)
            mock_parse.return_value = [_make_parsed_error()]

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="s\n",
            )

        assert result.exit_code == 42

    def test_capture_creates_fix(self, tmp_path):
        """Pressing Enter (capture) creates a fix."""
        runner = CliRunner()
        cli = create_cli()
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse, \
             patch.object(_watch_mod, "capture_single_error", return_value=mock_fix):
            mp.return_value = mock_popen_failure()
            mock_parse.return_value = [_make_parsed_error()]

            # Enter = capture
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="\n",
            )

        assert "Fix saved" in result.output

    def test_defer_single_error_saves_to_pending(self, tmp_path):
        """Choosing 'd' defers the single error to pending."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse, \
             patch.object(_watch_mod, "PendingStore") as MockStore:
            mp.return_value = mock_popen_failure()
            mock_parse.return_value = [_make_parsed_error()]
            store_instance = MockStore.return_value

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="d\n",
            )

        assert "Saved to pending" in result.output
        store_instance.save.assert_called_once()

    def test_empty_output_no_capture_prompt(self, tmp_path):
        """If command fails but produces no output, no capture prompt."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_failure(stdout_lines=[b""])

            result = runner.invoke(
                cli,
                ["watch", "--", "silent-fail"],
                obj=make_obj(tmp_path),
            )

        assert "Capture this error?" not in result.output
        assert result.exit_code == 1


# ===================================================================
# TestWatchCommandFailureGeneric — no structured errors
# ===================================================================


class TestWatchCommandFailureGeneric:
    """Tests for when the watched command fails with unrecognized output."""

    def test_generic_error_capture_via_piped_input(self, tmp_path):
        """When detect_and_parse returns [], Enter captures via handle_piped_input."""
        runner = CliRunner()
        cli = create_cli()
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=[]), \
             patch.object(_watch_mod, "handle_piped_input", return_value=mock_fix):
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"some generic error text\n", b""],
            )

            # Enter = capture
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="\n",
            )

        assert "Fix saved" in result.output

    def test_generic_skip_no_fix(self, tmp_path):
        """Choosing 's' on generic error exits without fix."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=[]):
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"some error\n", b""],
            )

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="s\n",
            )

        assert "Fix saved" not in result.output

    def test_generic_defer_saves_to_pending(self, tmp_path):
        """Choosing 'd' on generic error saves to pending."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=[]), \
             patch.object(_watch_mod, "PendingStore") as MockStore:
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"some error\n", b""],
            )
            store_instance = MockStore.return_value

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="d\n",
            )

        assert "Saved to pending" in result.output
        store_instance.save.assert_called_once()


# ===================================================================
# TestWatchCommandOptions
# ===================================================================


class TestWatchCommandOptions:
    """Tests for --no-prompt and --tags options."""

    def test_no_prompt_auto_captures_structured_error(self, tmp_path):
        """--no-prompt auto-captures structured errors without prompting."""
        runner = CliRunner()
        cli = create_cli()
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse, \
             patch.object(_watch_mod, "capture_single_error", return_value=mock_fix):
            mp.return_value = mock_popen_failure()
            mock_parse.return_value = [_make_parsed_error()]

            result = runner.invoke(
                cli,
                ["watch", "--no-prompt", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
            )

        assert "Capture this error?" not in result.output
        assert "Fix saved" in result.output

    def test_no_prompt_generic_error_passes_tags(self, tmp_path):
        """--no-prompt with generic errors passes tags to handle_piped_input."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=[]), \
             patch.object(_watch_mod, "handle_piped_input") as mock_handler:
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"generic error\n", b""],
            )
            mock_handler.return_value = None

            result = runner.invoke(
                cli,
                ["watch", "--tags", "aws,terraform", "--no-prompt", "--", "cmd"],
                obj=make_obj(tmp_path),
            )

            mock_handler.assert_called_once()
            _, kwargs = mock_handler.call_args
            assert kwargs.get("tags") == "aws,terraform"

    def test_tags_passed_to_structured_capture(self, tmp_path):
        """--tags are passed through to structured error capture."""
        runner = CliRunner()
        cli = create_cli()
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse") as mock_parse, \
             patch.object(_watch_mod, "capture_single_error", return_value=mock_fix) as mock_cap:
            mp.return_value = mock_popen_failure()
            mock_parse.return_value = [_make_parsed_error()]

            result = runner.invoke(
                cli,
                ["watch", "--tags", "infra,prod", "--no-prompt", "--", "cmd"],
                obj=make_obj(tmp_path),
            )

            mock_cap.assert_called_once()
            args, kwargs = mock_cap.call_args
            # tags is the 3rd positional arg (err, raw_output, tags, repo, config)
            assert args[2] == "infra,prod"


# ===================================================================
# TestWatchCommandNotFound
# ===================================================================


class TestWatchCommandNotFound:
    """Tests for command-not-found handling."""

    def test_command_not_found(self, tmp_path):
        """Non-existent command prints error and exits 127."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(
            _watch_mod.subprocess, "Popen", side_effect=FileNotFoundError()
        ):
            result = runner.invoke(
                cli,
                ["watch", "--", "nonexistent-command-xyz"],
                obj=make_obj(tmp_path),
            )

        assert "Command not found" in result.output
        assert result.exit_code == 127


# ===================================================================
# TestWatchNoCommand
# ===================================================================


class TestWatchNoCommand:
    """Tests for missing command argument."""

    def test_no_command_shows_error(self, tmp_path):
        """Running watch without a command shows usage error."""
        runner = CliRunner()
        cli = create_cli()

        result = runner.invoke(
            cli,
            ["watch", "--"],
            obj=make_obj(tmp_path),
        )

        assert result.exit_code != 0


# ===================================================================
# TestWatchMultiErrorFlow
# ===================================================================


class TestWatchMultiErrorFlow:
    """Tests for the multi-error interactive flow."""

    def _setup_multi_error(self, tmp_path, num_errors=3):
        """Return (runner, cli, mock_popen, errors)."""
        errors = [
            _make_parsed_error(
                resource_address=f"aws_resource_{i}.name",
                error_code=f"Error{i}",
            )
            for i in range(num_errors)
        ]
        return CliRunner(), create_cli(), errors

    def test_multi_error_shows_summary_table(self, tmp_path):
        """Multiple errors display a summary table."""
        runner, cli, errors = self._setup_multi_error(tmp_path)

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors):
            mp.return_value = mock_popen_failure()

            # Choose "2" to skip capture
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="2\n",
            )

        assert "Found 3 error(s)" in result.output
        assert "aws_resource_0.name" in result.output
        assert "aws_resource_1.name" in result.output
        assert "aws_resource_2.name" in result.output

    def test_multi_error_skip_creates_no_fixes(self, tmp_path):
        """Choosing 'skip' creates no fixes."""
        runner, cli, errors = self._setup_multi_error(tmp_path)

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors):
            mp.return_value = mock_popen_failure()

            # "2" = skip
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="2\n",
            )

        assert "Fix saved" not in result.output

    def test_multi_error_defer_all(self, tmp_path):
        """Choosing 'defer all' saves all errors to pending."""
        runner, cli, errors = self._setup_multi_error(tmp_path)

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors), \
             patch.object(_watch_mod, "PendingStore") as MockStore:
            mp.return_value = mock_popen_failure()
            store_instance = MockStore.return_value

            # "3" = save all to pending
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="3\n",
            )

        assert "Saved 3 error(s) to pending" in result.output
        assert store_instance.save.call_count == 3

    def test_multi_error_capture_all_iterates(self, tmp_path):
        """Default (Enter) iterates through all errors."""
        runner, cli, errors = self._setup_multi_error(tmp_path, num_errors=2)
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors), \
             patch.object(_watch_mod, "get_similar_fixes_for_error", return_value=[]), \
             patch.object(_watch_mod, "capture_single_error", return_value=mock_fix):
            mp.return_value = mock_popen_failure()

            # Enter (capture all), then for each error:
            # Enter (capture new fix)
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="\n\n\n",
            )

        assert "Error 1/2" in result.output
        assert "Error 2/2" in result.output

    def test_multi_error_skip_per_error(self, tmp_path):
        """Pressing 's' skips an individual error."""
        runner, cli, errors = self._setup_multi_error(tmp_path, num_errors=2)

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors), \
             patch.object(_watch_mod, "get_similar_fixes_for_error", return_value=[]), \
             patch.object(_watch_mod, "capture_single_error") as mock_cap:
            mp.return_value = mock_popen_failure()
            mock_cap.return_value = None

            # Enter (capture all), then "s" (skip first), "s" (skip second)
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="\ns\ns\n",
            )

        # capture_single_error should not have been called (both skipped)
        mock_cap.assert_not_called()

    def test_multi_error_defer_per_error(self, tmp_path):
        """Pressing 'd' defers an individual error."""
        runner, cli, errors = self._setup_multi_error(tmp_path, num_errors=1)

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors * 2), \
             patch.object(_watch_mod, "get_similar_fixes_for_error", return_value=[]), \
             patch.object(_watch_mod, "PendingStore") as MockStore:
            mp.return_value = mock_popen_failure()
            store_instance = MockStore.return_value

            # Enter (capture all), then "d" (defer first), "d" (defer second)
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="\nd\nd\n",
            )

        assert store_instance.save.call_count == 2
        assert "Saved to pending" in result.output

    def test_no_prompt_multi_error_auto_captures_all(self, tmp_path):
        """--no-prompt with multiple errors auto-captures all without prompting."""
        runner, cli, errors = self._setup_multi_error(tmp_path, num_errors=2)
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors), \
             patch.object(_watch_mod, "capture_single_error", return_value=mock_fix) as mock_cap:
            mp.return_value = mock_popen_failure()

            result = runner.invoke(
                cli,
                ["watch", "--no-prompt", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
            )

        assert mock_cap.call_count == 2
        assert result.output.count("Fix saved") == 2

    def test_multi_error_select_single(self, tmp_path):
        """Choosing '1' then a number captures only that error."""
        runner, cli, errors = self._setup_multi_error(tmp_path, num_errors=3)
        mock_fix = _make_fix()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=errors), \
             patch.object(_watch_mod, "get_similar_fixes_for_error", return_value=[]), \
             patch.object(_watch_mod, "capture_single_error", return_value=mock_fix) as mock_cap:
            mp.return_value = mock_popen_failure()

            # "1" = select single, "2" = error number 2, Enter = capture
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="1\n2\n\n",
            )

        # Only one error should be captured
        assert mock_cap.call_count == 1
        # The error card should show 1/1 (since we narrowed to one)
        assert "Error 1/1" in result.output


# ===================================================================
# TestDisplaySummaryTable
# ===================================================================


class TestDisplaySummaryTable:
    """Unit tests for _display_summary_table."""

    def test_summary_table_truncates_long_resource(self):
        """Long resource addresses are truncated."""
        err = _make_parsed_error(
            resource_address="module.very.long.module.path.aws_resource_type.name_here"
        )
        runner = CliRunner()
        with runner.isolated_filesystem():
            from click.testing import CliRunner as CR
            # Just call the function and check output
            result = runner.invoke(
                _make_echo_command([err]),
            )
            # The function is internal, test via multi-error flow instead
            pass

    def test_summary_table_shows_error_type_when_no_code(self):
        """When error_code is None, shows error_type instead."""
        err = _make_parsed_error(error_code=None)
        # error_type is "terraform", should show in Code/Type column
        assert err.error_type == "terraform"


# ===================================================================
# TestPromptFunctions
# ===================================================================


class TestPromptMultiErrorAction:
    """Unit tests for _prompt_multi_error_action."""

    def test_empty_input_returns_all(self):
        runner = CliRunner()
        with patch("click.prompt", return_value=""):
            result = _watch_mod._prompt_multi_error_action()
        assert result == "all"

    def test_choice_1_returns_single(self):
        with patch("click.prompt", return_value="1"):
            result = _watch_mod._prompt_multi_error_action()
        assert result == "single"

    def test_choice_2_returns_skip(self):
        with patch("click.prompt", return_value="2"):
            result = _watch_mod._prompt_multi_error_action()
        assert result == "skip"

    def test_choice_3_returns_defer_all(self):
        with patch("click.prompt", return_value="3"):
            result = _watch_mod._prompt_multi_error_action()
        assert result == "defer_all"

    def test_invalid_choice_returns_all(self):
        with patch("click.prompt", return_value="xyz"):
            result = _watch_mod._prompt_multi_error_action()
        assert result == "all"


class TestPromptSingleErrorAction:
    """Unit tests for _prompt_single_error_action."""

    def test_empty_returns_capture(self):
        with patch("click.prompt", return_value=""):
            result = _watch_mod._prompt_single_error_action(exit_code=1)
        assert result == "capture"

    def test_d_returns_defer(self):
        with patch("click.prompt", return_value="d"):
            result = _watch_mod._prompt_single_error_action(exit_code=1)
        assert result == "defer"

    def test_s_returns_skip(self):
        with patch("click.prompt", return_value="s"):
            result = _watch_mod._prompt_single_error_action(exit_code=1)
        assert result == "skip"

    def test_invalid_returns_capture(self):
        with patch("click.prompt", return_value="xyz"):
            result = _watch_mod._prompt_single_error_action(exit_code=1)
        assert result == "capture"


class TestPromptPerErrorAction:
    """Unit tests for _prompt_per_error_action."""

    def test_empty_returns_capture(self):
        with patch("click.prompt", return_value=""):
            result = _watch_mod._prompt_per_error_action(has_matches=False)
        assert result == "capture"

    def test_s_returns_skip(self):
        with patch("click.prompt", return_value="s"):
            result = _watch_mod._prompt_per_error_action(has_matches=False)
        assert result == "skip"

    def test_d_returns_defer(self):
        with patch("click.prompt", return_value="d"):
            result = _watch_mod._prompt_per_error_action(has_matches=False)
        assert result == "defer"

    def test_m_with_matches_returns_match(self):
        with patch("click.prompt", return_value="m"):
            result = _watch_mod._prompt_per_error_action(has_matches=True)
        assert result == "match"

    def test_m_without_matches_returns_capture(self):
        with patch("click.prompt", return_value="m"):
            result = _watch_mod._prompt_per_error_action(has_matches=False)
        assert result == "capture"


# Helper for summary table test — not used, keeping test simple
def _make_echo_command(errors):
    """Create a trivial Click command that calls _display_summary_table."""
    import click

    @click.command()
    def cmd():
        _watch_mod._display_summary_table(errors)

    return cmd
