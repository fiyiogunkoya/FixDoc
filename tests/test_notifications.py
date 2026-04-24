"""Tests for fixdoc notifications module."""

import importlib
import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from fixdoc.models import Fix
from fixdoc.notifications import _build_blocks, _slack_post, post_slack_notification
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


def _make_fix(**kwargs):
    """Create a Fix for testing."""
    defaults = dict(
        issue="AccessDenied on aws_iam_role.app",
        resolution="Added role binding in IAM console",
        tags="aws,terraform",
    )
    defaults.update(kwargs)
    return Fix(**defaults)


class TestBuildBlocks:
    """Tests for _build_blocks Slack block builder."""

    def test_basic_blocks_no_suggestions(self):
        """Blocks contain header and error list, no fix section."""
        entries = [_make_entry()]
        blocks = _build_blocks(entries, [], cwd="/project", command="terraform apply")

        assert len(blocks) == 3  # header + divider + error list
        header = blocks[0]["text"]["text"]
        assert "1 error(s) detected" in header
        assert "terraform apply" in header
        assert "/project" in header

    def test_blocks_with_suggestions(self):
        """Blocks include fix suggestions section."""
        entries = [_make_entry()]
        fix = _make_fix()
        suggestions = [("aws_iam_role.app (AccessDenied)", fix)]
        blocks = _build_blocks(entries, suggestions)

        # header + divider + errors + divider + fixes
        assert len(blocks) == 5
        fix_block = blocks[4]["text"]["text"]
        assert "Known fixes" in fix_block
        assert fix.id[:8] in fix_block

    def test_caps_at_5_errors(self):
        """More than 5 entries shows '... and N more'."""
        entries = [_make_entry(error_id=f"err_{i}") for i in range(8)]
        blocks = _build_blocks(entries, [])

        error_text = blocks[2]["text"]["text"]
        assert "... and 3 more" in error_text

    def test_caps_at_3_suggestions(self):
        """Only top 3 suggestions appear in blocks."""
        entries = [_make_entry()]
        fixes = [_make_fix(resolution=f"Fix number {i}") for i in range(5)]
        suggestions = [(f"entry_{i}", fix) for i, fix in enumerate(fixes)]
        blocks = _build_blocks(entries, suggestions)

        fix_block = blocks[4]["text"]["text"]
        # Should have exactly 3 fix lines (plus header line)
        fix_lines = [l for l in fix_block.split("\n") if l.strip().startswith("`")]
        assert len(fix_lines) == 3


class TestSlackPost:
    """Tests for _slack_post API call."""

    def test_success(self):
        """Successful POST returns response dict."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("fixdoc.notifications.urllib.request.urlopen", return_value=mock_resp):
            result = _slack_post("chat.postMessage", "token", {"channel": "C123"})

        assert result["ok"] is True

    def test_failure_returns_error(self):
        """Non-429 HTTP error returns error dict."""
        error = urllib.error.HTTPError(
            url="", code=403, msg="Forbidden", hdrs=MagicMock(), fp=None
        )

        with patch("fixdoc.notifications.urllib.request.urlopen", side_effect=error):
            result = _slack_post("chat.postMessage", "token", {})

        assert result["ok"] is False
        assert "403" in result["error"]

    def test_retries_on_429(self):
        """429 responses trigger retry."""
        error_429 = urllib.error.HTTPError(
            url="", code=429, msg="Rate limited",
            hdrs=MagicMock(**{"get.return_value": "0"}), fp=None,
        )
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("fixdoc.notifications.urllib.request.urlopen",
                    side_effect=[error_429, mock_resp]), \
             patch("fixdoc.notifications.time.sleep"):
            result = _slack_post("chat.postMessage", "token", {})

        assert result["ok"] is True

    def test_handles_max_retries(self):
        """After max retries on 429, returns rate_limited error."""
        error_429 = urllib.error.HTTPError(
            url="", code=429, msg="Rate limited",
            hdrs=MagicMock(**{"get.return_value": "0"}), fp=None,
        )

        with patch("fixdoc.notifications.urllib.request.urlopen",
                    side_effect=[error_429, error_429, error_429]), \
             patch("fixdoc.notifications.time.sleep"):
            result = _slack_post("chat.postMessage", "token", {})

        assert result["ok"] is False
        assert result["error"] == "rate_limited"


class TestPostSlackNotification:
    """Tests for post_slack_notification high-level function."""

    def test_returns_true_on_success(self):
        """Successful notification returns True."""
        entries = [_make_entry()]

        with patch("fixdoc.notifications._slack_post", return_value={"ok": True}):
            result = post_slack_notification(
                token="xoxb-test", channel="C123",
                entries=entries, suggestions=[],
            )

        assert result is True

    def test_returns_false_on_failure(self):
        """Failed notification returns False."""
        entries = [_make_entry()]

        with patch("fixdoc.notifications._slack_post", return_value={"ok": False, "error": "not_authed"}):
            result = post_slack_notification(
                token="xoxb-test", channel="C123",
                entries=entries, suggestions=[],
            )

        assert result is False


_watch_mod = importlib.import_module("fixdoc.commands.watch")


class TestWatchSlackNotification:
    """Tests for _maybe_notify_slack helper and --notify flag."""

    def test_notify_flag_triggers_notification(self):
        """notify_flag=True with config triggers post_slack_notification."""
        from fixdoc.config import FixDocConfig, NotificationConfig

        entries = [_make_entry()]
        suggestions = [("aws_iam_role.app", _make_fix())]
        config = FixDocConfig(
            notification=NotificationConfig(slack_channel="C123"),
        )

        with patch.dict("os.environ", {"SLACK_TOKEN": "xoxb-test"}), \
             patch("fixdoc.notifications.post_slack_notification", return_value=True) as mock_notify:
            _watch_mod._maybe_notify_slack(
                entries, suggestions, config, "terraform apply", True
            )

        mock_notify.assert_called_once()

    def test_no_notify_no_notification(self):
        """notify_flag=False + slack_enabled=False means no notification."""
        from fixdoc.config import FixDocConfig

        entries = [_make_entry()]
        suggestions = [("aws_iam_role.app", _make_fix())]
        config = FixDocConfig()

        with patch("fixdoc.notifications.post_slack_notification") as mock_notify:
            _watch_mod._maybe_notify_slack(
                entries, suggestions, config, "terraform apply", False
            )

        mock_notify.assert_not_called()
