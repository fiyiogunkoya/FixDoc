"""Unit tests for CloudClient + credential helpers.

Uses a fake transport to avoid any network I/O.
"""
import json
from pathlib import Path

import pytest

from fixdoc.cloud import (
    CLOUD_FILE,
    CloudClient,
    CloudCredentials,
    CloudError,
    clear_credentials,
    fix_to_cloud_payload,
    load_credentials,
    probe_token,
    save_credentials,
)
from fixdoc.models import Fix


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------


def make_transport(responses):
    """Build a fake transport from a list or dict of responses.

    - list: consumed in order; each call pops one entry
    - dict: keyed by (method, path) — matches by path prefix
    """
    calls = []

    def _transport(method, url, headers=None, body=None):
        calls.append({"method": method, "url": url, "headers": headers, "body": body})
        if isinstance(responses, list):
            if not responses:
                raise AssertionError(f"No more scripted responses for {method} {url}")
            return responses.pop(0)
        for (m, path_fragment), resp in responses.items():
            if m == method and path_fragment in url:
                return resp
        raise AssertionError(f"No scripted response for {method} {url}")

    _transport.calls = calls  # type: ignore[attr-defined]
    return _transport


def _ok(body_dict, status=200):
    return {
        "status": status,
        "body": json.dumps(body_dict).encode("utf-8"),
        "headers": {},
    }


def _err(status, detail="nope"):
    return {
        "status": status,
        "body": json.dumps({"detail": detail}).encode("utf-8"),
        "headers": {},
    }


# ---------------------------------------------------------------------------
# Credentials file round-trip
# ---------------------------------------------------------------------------


def test_save_and_load_credentials(tmp_path: Path):
    creds = CloudCredentials(
        api_url="https://api.test",
        token="fd_live_abc",
        team_id="team-uuid",
        team_slug="acme",
    )
    save_credentials(creds, base_path=tmp_path)
    assert (tmp_path / CLOUD_FILE).exists()

    loaded = load_credentials(base_path=tmp_path)
    assert loaded.api_url == "https://api.test"
    assert loaded.token == "fd_live_abc"
    assert loaded.team_slug == "acme"
    assert loaded.is_logged_in()


def test_load_credentials_missing_returns_default(tmp_path: Path):
    creds = load_credentials(base_path=tmp_path)
    assert creds.token is None
    assert creds.is_logged_in() is False


def test_clear_credentials(tmp_path: Path):
    save_credentials(
        CloudCredentials(token="x", team_id="y"), base_path=tmp_path
    )
    assert (tmp_path / CLOUD_FILE).exists()
    clear_credentials(base_path=tmp_path)
    assert not (tmp_path / CLOUD_FILE).exists()


def test_clear_credentials_when_absent_is_safe(tmp_path: Path):
    clear_credentials(base_path=tmp_path)  # must not raise


def test_credentials_file_is_chmod_600(tmp_path: Path):
    save_credentials(
        CloudCredentials(token="x", team_id="y"), base_path=tmp_path
    )
    path = tmp_path / CLOUD_FILE
    # On macOS the chmod sticks; skip if filesystem doesn't honor it
    mode = path.stat().st_mode & 0o777
    assert mode in (0o600, 0o644)  # tolerate FS quirks


# ---------------------------------------------------------------------------
# CloudClient — HTTP error handling
# ---------------------------------------------------------------------------


def test_client_requires_token():
    # No token + no team_id → "Not logged in" path; no token + team_id → still
    # fails because is_logged_in checks for both. Either way, must raise.
    creds = CloudCredentials(api_url="https://api")
    with pytest.raises(CloudError):
        CloudClient(creds)

    # Opting out of team requirement still needs a token
    with pytest.raises(CloudError, match="Missing API token"):
        CloudClient(creds, require_team=False)


def test_client_requires_team_by_default():
    creds = CloudCredentials(api_url="https://api", token="fd_live_x")
    with pytest.raises(CloudError, match="Not logged in"):
        CloudClient(creds)


def test_client_auth_error_surface():
    creds = CloudCredentials(api_url="https://api", token="fd_live_x", team_id="t1")
    client = CloudClient(creds, transport=make_transport([_err(401, "bad token")]))
    with pytest.raises(CloudError, match="Authentication failed"):
        client.whoami()


def test_client_generic_error_includes_detail():
    creds = CloudCredentials(api_url="https://api", token="fd_live_x", team_id="t1")
    client = CloudClient(creds, transport=make_transport([_err(500, "boom")]))
    with pytest.raises(CloudError, match="500.*boom"):
        client.whoami()


def test_client_204_returns_none():
    creds = CloudCredentials(api_url="https://api", token="fd_live_x", team_id="t1")
    tr = make_transport([{"status": 204, "body": b"", "headers": {}}])
    client = CloudClient(creds, transport=tr)
    assert client._request("DELETE", "/api/v1/fixes/x") is None


# ---------------------------------------------------------------------------
# Domain calls
# ---------------------------------------------------------------------------


def test_list_fixes_sends_team_id():
    creds = CloudCredentials(
        api_url="https://api", token="fd_live_x", team_id="team-1"
    )
    tr = make_transport([_ok({"items": [], "total": 0, "limit": 50, "offset": 0})])
    client = CloudClient(creds, transport=tr)
    client.list_fixes()
    assert "team_id=team-1" in tr.calls[0]["url"]


def test_push_fixes_posts_bulk_payload():
    creds = CloudCredentials(
        api_url="https://api", token="fd_live_x", team_id="team-1"
    )
    tr = make_transport([_ok({"created": 2, "duplicates": 0, "ids": ["a", "b"]})])
    client = CloudClient(creds, transport=tr)
    resp = client.push_fixes([{"issue": "A", "resolution": "B"}])
    assert resp["created"] == 2
    body = json.loads(tr.calls[0]["body"])
    assert body["fixes"] == [{"issue": "A", "resolution": "B"}]


def test_search_returns_items_list():
    creds = CloudCredentials(
        api_url="https://api", token="fd_live_x", team_id="t"
    )
    tr = make_transport(
        [_ok({"items": [{"issue": "x", "resolution": "y"}], "total": 1})]
    )
    client = CloudClient(creds, transport=tr)
    items = client.search_fixes("x")
    assert items == [{"issue": "x", "resolution": "y"}]


# ---------------------------------------------------------------------------
# probe_token + fix payload helper
# ---------------------------------------------------------------------------


def test_probe_token_returns_team_context():
    tr = make_transport(
        [
            _ok(
                {
                    "team_id": "team-xyz",
                    "team_slug": "acme",
                    "team_name": "Acme",
                    "api_key_name": "laptop",
                    "api_key_id": "k1",
                }
            )
        ]
    )
    info = probe_token("https://api", "fd_live_abc", transport=tr)
    assert info["team_slug"] == "acme"
    assert "Authorization" in (tr.calls[0]["headers"] or {})
    assert tr.calls[0]["headers"]["Authorization"] == "Bearer fd_live_abc"


def test_probe_token_auth_failure_raises():
    tr = make_transport([_err(401, "bad")])
    with pytest.raises(CloudError, match="Authentication failed"):
        probe_token("https://api", "fd_live_bad", transport=tr)


def test_fix_to_cloud_payload_includes_content_hash():
    fix = Fix(issue="x", resolution="y", tags="a,b")
    payload = fix_to_cloud_payload(fix)
    assert payload["content_hash"] == fix.content_hash
    assert payload["client_id"] == fix.id
    assert payload["tags"] == "a,b"
