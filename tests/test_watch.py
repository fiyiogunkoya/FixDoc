"""Tests for the fixdoc watch command."""

import importlib
import subprocess
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from fixdoc.cli import create_cli
from fixdoc.config import FixDocConfig

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


class TestWatchCommandFailure:
    """Tests for when the watched command fails."""

    def test_failed_command_prompts_capture(self, tmp_path):
        """A failed command asks the user if they want to capture."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_failure()

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="n\n",
            )

        assert "Command failed (exit code 1)" in result.output

    def test_declined_capture_no_fix_created(self, tmp_path):
        """Declining capture creates no fix."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_failure()

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="n\n",
            )

        assert "Fix saved" not in result.output

    def test_exit_code_preserved_on_failure(self, tmp_path):
        """Non-zero exit code is preserved from the wrapped command."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_failure(
                exit_code=42,
                stdout_lines=[b"Error: exit 42\n", b""],
            )

            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input="n\n",
            )

        assert result.exit_code == 42

    def test_accepted_capture_creates_fix(self, tmp_path):
        """Accepting capture and providing details creates a fix."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"Error: something broke\n", b""],
            )

            # y to capture, then generic capture prompts:
            # issue, resolution, tags, notes
            user_input = "y\nthe thing broke\nfixed it\ngeneric\n\n"
            result = runner.invoke(
                cli,
                ["watch", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input=user_input,
            )

        assert "Fix saved" in result.output

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


class TestWatchCommandOptions:
    """Tests for --no-prompt and --tags options."""

    def test_no_prompt_skips_confirmation(self, tmp_path):
        """--no-prompt goes straight to capture flow without asking."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp:
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"Error: something broke\n", b""],
            )

            # No "y" needed — goes straight to capture prompts
            user_input = "the thing broke\nfixed it\ngeneric\n\n"
            result = runner.invoke(
                cli,
                ["watch", "--no-prompt", "--", "failing-cmd"],
                obj=make_obj(tmp_path),
                input=user_input,
            )

        assert "Capture this error?" not in result.output
        assert "Fix saved" in result.output

    def test_tags_passed_through(self, tmp_path):
        """--tags flag is passed through to the capture handler."""
        runner = CliRunner()
        cli = create_cli()

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "handle_piped_input") as mock_handler:
            mp.return_value = mock_popen_failure(
                stdout_lines=[b"Error: something broke\n", b""],
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
