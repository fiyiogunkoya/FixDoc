"""Tests for fixdoc diagnosis module."""

import importlib
from unittest.mock import patch, MagicMock

import pytest

from fixdoc.pending import PendingEntry


def _make_entry(**kwargs):
    """Create a PendingEntry for testing."""
    defaults = dict(
        error_id="abc123",
        error_type="terraform",
        short_message="Error: access denied",
        error_excerpt="Error: access denied on aws_iam_role.app",
        tags="aws,terraform",
        resource_address="aws_iam_role.app",
        error_code="AccessDenied",
        command="terraform apply",
        cwd="/project",
    )
    defaults.update(kwargs)
    return PendingEntry(**defaults)


class TestDiagnoseError:
    """Tests for the diagnose_error function."""

    def test_returns_text_on_success(self):
        """Mock anthropic returns text diagnosis."""
        from fixdoc.diagnosis import diagnose_error

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="- Root cause: IAM misconfiguration\n- Fix: Add role binding")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            import anthropic
            anthropic.Anthropic.return_value = mock_client

            result = diagnose_error(_make_entry(), api_key="test-key")

        assert result is not None
        assert "Root cause" in result

    def test_no_api_key_returns_none(self):
        """No API key returns None."""
        from fixdoc.diagnosis import diagnose_error

        with patch.dict("os.environ", {}, clear=True):
            result = diagnose_error(_make_entry(), api_key=None)

        # Without anthropic installed or key, returns None
        assert result is None

    def test_import_error_returns_none(self):
        """When anthropic is not installed, returns None."""
        from fixdoc.diagnosis import diagnose_error

        with patch.dict("sys.modules", {"anthropic": None}):
            # Force reimport to hit ImportError
            import fixdoc.diagnosis
            importlib.reload(fixdoc.diagnosis)
            result = fixdoc.diagnosis.diagnose_error(_make_entry(), api_key="test-key")

        # Restore module
        importlib.reload(fixdoc.diagnosis)
        assert result is None

    def test_api_failure_returns_none(self):
        """API exception returns None gracefully."""
        from fixdoc.diagnosis import diagnose_error

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            import anthropic
            anthropic.Anthropic.return_value = mock_client

            result = diagnose_error(_make_entry(), api_key="test-key")

        assert result is None

    def test_includes_resource_in_prompt(self):
        """Prompt includes resource_address when available."""
        from fixdoc.diagnosis import diagnose_error

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="diagnosis")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            import anthropic
            anthropic.Anthropic.return_value = mock_client

            diagnose_error(
                _make_entry(resource_address="aws_s3_bucket.data"),
                api_key="test-key",
            )

        call_args = mock_client.messages.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "aws_s3_bucket.data" in prompt

    def test_truncates_excerpt(self):
        """Long error excerpts are truncated to 1500 chars."""
        from fixdoc.diagnosis import diagnose_error

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="diagnosis")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        long_excerpt = "x" * 3000
        entry = _make_entry(error_excerpt=long_excerpt)

        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            import anthropic
            anthropic.Anthropic.return_value = mock_client

            diagnose_error(entry, api_key="test-key")

        call_args = mock_client.messages.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        # The prompt should not contain the full 3000 chars
        assert len(prompt) < 3000


class TestDiagnoseErrors:
    """Tests for the diagnose_errors batch function."""

    def test_limits_to_max_errors(self):
        """Only diagnose up to max_errors entries."""
        from fixdoc.diagnosis import diagnose_errors

        entries = [_make_entry(error_id=f"err_{i}") for i in range(5)]

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="diagnosis")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            import anthropic
            anthropic.Anthropic.return_value = mock_client

            results = diagnose_errors(entries, api_key="test-key", max_errors=3)

        assert len(results) == 3
        assert mock_client.messages.create.call_count == 3


_watch_mod = importlib.import_module("fixdoc.commands.watch")


class TestWatchDiagnosis:
    """Tests for --diagnose flag integration in watch command."""

    def test_diagnose_flag_calls_diagnosis(self, tmp_path):
        """--diagnose flag triggers _diagnose_errors_inline."""
        from click.testing import CliRunner
        from fixdoc.cli import create_cli
        from fixdoc.config import FixDocConfig
        from fixdoc.parsers.base import ParsedError, CloudProvider

        runner = CliRunner()
        cli = create_cli()

        err = ParsedError(
            error_type="terraform",
            error_message="access denied",
            raw_output="Error: access denied",
            resource_address="aws_iam_role.app",
            error_code="AccessDenied",
            cloud_provider=CloudProvider.AWS,
        )

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=[err]), \
             patch.object(_watch_mod, "PendingStore") as MockStore, \
             patch.object(_watch_mod, "_diagnose_errors_inline") as mock_diag:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout.readline.side_effect = [b"Error: access denied\n", b""]
            mock_proc.wait.return_value = 1
            mp.return_value = mock_proc
            MockStore.return_value = MagicMock()

            result = runner.invoke(
                cli,
                ["watch", "--diagnose", "--no-prompt", "--", "failing-cmd"],
                obj={
                    "base_path": tmp_path,
                    "config": FixDocConfig(),
                    "config_manager": MagicMock(),
                },
            )

        mock_diag.assert_called_once()

    def test_no_diagnose_flag_no_diagnosis(self, tmp_path):
        """Without --diagnose flag, no diagnosis is shown."""
        from click.testing import CliRunner
        from fixdoc.cli import create_cli
        from fixdoc.config import FixDocConfig
        from fixdoc.parsers.base import ParsedError, CloudProvider

        runner = CliRunner()
        cli = create_cli()

        err = ParsedError(
            error_type="terraform",
            error_message="access denied",
            raw_output="Error: access denied",
            resource_address="aws_iam_role.app",
            error_code="AccessDenied",
            cloud_provider=CloudProvider.AWS,
        )

        with patch.object(_watch_mod.subprocess, "Popen") as mp, \
             patch.object(_watch_mod, "detect_and_parse", return_value=[err]), \
             patch.object(_watch_mod, "PendingStore") as MockStore, \
             patch.object(_watch_mod, "_diagnose_errors_inline") as mock_diag:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout.readline.side_effect = [b"Error: access denied\n", b""]
            mock_proc.wait.return_value = 1
            mp.return_value = mock_proc
            MockStore.return_value = MagicMock()

            result = runner.invoke(
                cli,
                ["watch", "--no-prompt", "--", "failing-cmd"],
                obj={
                    "base_path": tmp_path,
                    "config": FixDocConfig(),
                    "config_manager": MagicMock(),
                },
            )

        mock_diag.assert_not_called()

    def test_diagnose_no_api_key_shows_warning(self, tmp_path):
        """Missing ANTHROPIC_API_KEY prints warning to stderr."""
        from fixdoc.config import FixDocConfig

        entries = [_make_entry()]
        config = FixDocConfig()

        with patch.dict("os.environ", {}, clear=True):
            from click.testing import CliRunner

            runner = CliRunner(mix_stderr=False)
            # Call the helper directly
            from io import StringIO
            import click

            output = StringIO()
            with patch("click.echo") as mock_echo:
                _watch_mod._diagnose_errors_inline(entries, config)

            # Check that warning was issued
            warning_calls = [
                c for c in mock_echo.call_args_list
                if c[1].get("err") and "ANTHROPIC_API_KEY" in str(c[0][0])
            ]
            assert len(warning_calls) >= 1
