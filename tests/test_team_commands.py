"""CliRunner tests for `fixdoc login`, `fixdoc logout`, and `fixdoc team *`.

Network is mocked by patching `fixdoc.cloud._default_transport` with a fake.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from fixdoc.cli import create_cli
from fixdoc.cloud import (
    CloudCredentials,
    load_credentials,
    save_credentials,
)
from fixdoc.models import Fix
from fixdoc.storage import FixRepository


def _fake_response(body_dict, status=200):
    return {
        "status": status,
        "body": json.dumps(body_dict).encode("utf-8"),
        "headers": {},
    }


def _fake_transport(responses):
    calls = []

    def _transport(method, url, headers=None, body=None):
        calls.append((method, url, headers, body))
        if not responses:
            raise AssertionError(f"Unscripted call: {method} {url}")
        return responses.pop(0)

    _transport.calls = calls
    return _transport


# ---------------------------------------------------------------------------
# login / logout
# ---------------------------------------------------------------------------


def test_login_saves_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))

    tr = _fake_transport(
        [
            _fake_response(
                {
                    "team_id": "team-1",
                    "team_slug": "acme",
                    "team_name": "Acme",
                    "api_key_name": "laptop",
                    "api_key_id": "k1",
                }
            )
        ]
    )
    runner = CliRunner()
    with patch("fixdoc.cloud._default_transport", tr):
        result = runner.invoke(
            create_cli(),
            ["login", "--api-url", "https://api.test", "--token", "fd_live_abc", "--no-browser"],
        )
    assert result.exit_code == 0, result.output
    assert "Logged in" in result.output
    assert "acme" in result.output

    creds = load_credentials(tmp_path)
    assert creds.token == "fd_live_abc"
    assert creds.team_slug == "acme"


def test_login_rejects_bad_token(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    tr = _fake_transport([_fake_response({"detail": "bad"}, status=401)])
    runner = CliRunner()
    with patch("fixdoc.cloud._default_transport", tr):
        result = runner.invoke(
            create_cli(),
            ["login", "--api-url", "https://api.test", "--token", "fd_live_bad", "--no-browser"],
        )
    assert result.exit_code != 0
    assert "Authentication failed" in result.output


def test_logout_removes_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    save_credentials(
        CloudCredentials(api_url="x", token="t", team_id="team-1", team_slug="acme"),
        base_path=tmp_path,
    )
    runner = CliRunner()
    result = runner.invoke(create_cli(), ["logout"])
    assert result.exit_code == 0
    assert "Logged out" in result.output
    assert load_credentials(tmp_path).token is None


# ---------------------------------------------------------------------------
# team status
# ---------------------------------------------------------------------------


def test_team_status_not_logged_in(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(create_cli(), ["team", "status"])
    assert result.exit_code == 0
    assert "Not logged in" in result.output


def test_team_status_shows_context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    save_credentials(
        CloudCredentials(
            api_url="https://api.test",
            token="fd_live_x",
            team_id="t",
            team_slug="acme",
        ),
        base_path=tmp_path,
    )
    runner = CliRunner()
    result = runner.invoke(create_cli(), ["team", "status"])
    assert result.exit_code == 0
    assert "https://api.test" in result.output
    assert "acme" in result.output


# ---------------------------------------------------------------------------
# team push
# ---------------------------------------------------------------------------


def _seed_logged_in(tmp_path: Path) -> None:
    save_credentials(
        CloudCredentials(
            api_url="https://api.test",
            token="fd_live_x",
            team_id="t",
            team_slug="acme",
        ),
        base_path=tmp_path,
    )


def test_team_push_no_fixes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    _seed_logged_in(tmp_path)
    runner = CliRunner()
    result = runner.invoke(create_cli(), ["team", "push"])
    assert result.exit_code == 0
    assert "No fixes to push" in result.output


def test_team_push_requires_login(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    repo = FixRepository(tmp_path)
    repo.save(Fix(issue="A", resolution="B"))
    runner = CliRunner()
    result = runner.invoke(create_cli(), ["team", "push"])
    assert result.exit_code != 0
    assert "login" in result.output.lower()


def test_team_push_dry_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    _seed_logged_in(tmp_path)
    repo = FixRepository(tmp_path)
    repo.save(Fix(issue="A", resolution="B"))
    repo.save(Fix(issue="C", resolution="D"))
    runner = CliRunner()
    result = runner.invoke(create_cli(), ["team", "push", "--dry-run"])
    assert result.exit_code == 0
    assert "Would push 2" in result.output


def test_team_push_uploads_fixes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    _seed_logged_in(tmp_path)
    repo = FixRepository(tmp_path)
    repo.save(Fix(issue="A", resolution="B"))

    tr = _fake_transport(
        [_fake_response({"created": 1, "duplicates": 0, "ids": ["x"]})]
    )
    runner = CliRunner()
    with patch("fixdoc.cloud._default_transport", tr):
        result = runner.invoke(create_cli(), ["team", "push"])

    assert result.exit_code == 0, result.output
    assert "1 new" in result.output
    # Credentials should now have a last_push_at
    creds = load_credentials(tmp_path)
    assert creds.last_push_at is not None


def test_team_push_skips_private_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    _seed_logged_in(tmp_path)
    repo = FixRepository(tmp_path)
    private = Fix(issue="secret", resolution="fix", is_private=True)
    public = Fix(issue="ok", resolution="fix")
    repo.save(private)
    repo.save(public)

    tr = _fake_transport(
        [_fake_response({"created": 1, "duplicates": 0, "ids": ["x"]})]
    )
    runner = CliRunner()
    with patch("fixdoc.cloud._default_transport", tr):
        result = runner.invoke(create_cli(), ["team", "push"])

    assert result.exit_code == 0
    # Only one fix pushed — body should reflect that
    _, _, _, body = tr.calls[0]
    parsed = json.loads(body)
    assert len(parsed["fixes"]) == 1


# ---------------------------------------------------------------------------
# team pull
# ---------------------------------------------------------------------------


def test_team_pull_adds_new_fixes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    _seed_logged_in(tmp_path)

    remote = {
        "items": [
            {
                "id": "server-1",
                "issue": "remote issue",
                "resolution": "remote fix",
                "tags": ["aws", "s3"],
                "notes": None,
                "author": None,
                "author_email": None,
                "is_private": False,
                "source_error_ids": None,
                "memory_type": "fix",
                "content_hash": "abc",
                "error_excerpt": None,
            }
        ],
        "total": 1,
        "limit": 500,
        "offset": 0,
    }
    tr = _fake_transport([_fake_response(remote)])
    runner = CliRunner()
    with patch("fixdoc.cloud._default_transport", tr):
        result = runner.invoke(create_cli(), ["team", "pull"])

    assert result.exit_code == 0, result.output
    assert "Pulled 1" in result.output

    repo = FixRepository(tmp_path)
    fixes = repo.list_all()
    assert any(f.issue == "remote issue" for f in fixes)


# ---------------------------------------------------------------------------
# team search
# ---------------------------------------------------------------------------


def test_team_search_prints_matches(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIXDOC_HOME", str(tmp_path))
    _seed_logged_in(tmp_path)

    tr = _fake_transport(
        [
            _fake_response(
                {
                    "items": [
                        {
                            "issue": "BucketAlreadyExists",
                            "resolution": "Add random suffix to bucket name",
                            "tags": ["aws", "s3"],
                        }
                    ],
                    "total": 1,
                }
            )
        ]
    )
    runner = CliRunner()
    with patch("fixdoc.cloud._default_transport", tr):
        result = runner.invoke(create_cli(), ["team", "search", "bucket"])
    assert result.exit_code == 0, result.output
    assert "BucketAlreadyExists" in result.output
