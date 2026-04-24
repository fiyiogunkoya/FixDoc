"""CLI-side cloud client — talks to the FixDoc SaaS backend.

Credentials live in `~/.fixdoc/cloud.yaml` (separate from `config.yaml` to avoid
accidentally leaking tokens when users share their config). The file format:

    api_url: https://api.fixdoc.dev
    token: fd_live_xxxxxxxxxxxxxxxx
    team_id: 01JAAAAAAAAAAAAAAAAAAAAAAA
    team_slug: platform
    last_push_at: "2026-04-24T19:03:12+00:00"
    last_pull_at: "2026-04-24T19:03:12+00:00"

Transport is `urllib` (stdlib) with JSON to keep runtime deps minimal — same
pattern as the Notion/Slack importers. When httpx is available (backend dev),
callers can inject their own client via `CloudClient(http=...)`; tests use a
fake transport to avoid network.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .config import resolve_base_path


CLOUD_FILE = "cloud.yaml"
DEFAULT_API_URL = "https://api.fixdoc.dev"


@dataclass
class CloudCredentials:
    api_url: str = DEFAULT_API_URL
    token: Optional[str] = None
    team_id: Optional[str] = None
    team_slug: Optional[str] = None
    last_push_at: Optional[str] = None
    last_pull_at: Optional[str] = None

    def is_logged_in(self) -> bool:
        return bool(self.token and self.team_id)


class CloudError(RuntimeError):
    """Raised for any cloud API failure — network, HTTP, or auth."""


def _cloud_path(base_path: Optional[Path] = None) -> Path:
    return (base_path or resolve_base_path()) / CLOUD_FILE


def load_credentials(base_path: Optional[Path] = None) -> CloudCredentials:
    path = _cloud_path(base_path)
    if not path.exists():
        return CloudCredentials()
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, IOError):
        return CloudCredentials()
    return CloudCredentials(
        api_url=data.get("api_url", DEFAULT_API_URL),
        token=data.get("token"),
        team_id=data.get("team_id"),
        team_slug=data.get("team_slug"),
        last_push_at=data.get("last_push_at"),
        last_pull_at=data.get("last_pull_at"),
    )


def save_credentials(creds: CloudCredentials, base_path: Optional[Path] = None) -> None:
    base = base_path or resolve_base_path()
    base.mkdir(parents=True, exist_ok=True)
    path = base / CLOUD_FILE
    with open(path, "w") as f:
        yaml.safe_dump(asdict(creds), f, default_flow_style=False, sort_keys=False)
    # Tighten permissions — token is a secret
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_credentials(base_path: Optional[Path] = None) -> None:
    path = _cloud_path(base_path)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


HttpResponse = Dict[str, Any]
HttpTransport = Callable[[str, str, Optional[Dict[str, str]], Optional[bytes]], HttpResponse]


def _default_transport(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
) -> HttpResponse:
    """Minimal urllib-based HTTP. Returns `{status, body_bytes, headers}`."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {
                "status": resp.status,
                "body": resp.read(),
                "headers": dict(resp.headers),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "body": exc.read() if hasattr(exc, "read") else b"",
            "headers": dict(exc.headers or {}),
        }
    except urllib.error.URLError as exc:
        raise CloudError(f"Network error: {exc.reason}") from exc


class CloudClient:
    """Thin HTTP client for the FixDoc backend.

    All methods raise `CloudError` on non-2xx responses so callers can handle
    auth/network failures uniformly. Most methods require a fully-authenticated
    credential set; login probes use `probe_token()` instead.
    """

    def __init__(
        self,
        credentials: CloudCredentials,
        transport: Optional[HttpTransport] = None,
        *,
        require_team: bool = True,
    ) -> None:
        if require_team and not credentials.is_logged_in():
            raise CloudError("Not logged in — run `fixdoc login` first")
        if not credentials.token:
            raise CloudError("Missing API token")
        self.credentials = credentials
        self._transport = transport or _default_transport

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> Any:
        url = self.credentials.api_url.rstrip("/") + path
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            if query:
                url = f"{url}?{query}"

        headers = {
            "Authorization": f"Bearer {self.credentials.token}",
            "Accept": "application/json",
        }
        body_bytes: Optional[bytes] = None
        if json_body is not None:
            body_bytes = json.dumps(json_body, default=str).encode("utf-8")
            headers["Content-Type"] = "application/json"

        result = self._transport(method, url, headers, body_bytes)
        status = result.get("status", 0)
        raw = result.get("body") or b""

        if status in (401, 403):
            raise CloudError(
                "Authentication failed — token may be expired. Run `fixdoc login` again."
            )
        if status == 204:
            return None
        if not 200 <= status < 300:
            try:
                detail = json.loads(raw.decode("utf-8")).get("detail", raw.decode("utf-8", "replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = f"HTTP {status}"
            raise CloudError(f"Cloud API error ({status}): {detail}")

        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CloudError(f"Invalid JSON from cloud: {exc}") from exc

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    def whoami(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/auth/me")

    def cli_whoami(self) -> Dict[str, Any]:
        """Resolve team context for an API key. Raises `CloudError` on bad token."""
        return self._request("GET", "/api/v1/auth/cli-whoami")

    def list_fixes(
        self,
        *,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/fixes",
            params={"team_id": self.credentials.team_id, "q": q, "limit": limit, "offset": offset},
        )

    def push_fixes(self, fixes: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/fixes/bulk",
            params={"team_id": self.credentials.team_id},
            json_body={"fixes": fixes},
        )

    def pull_fixes(self, *, limit: int = 500) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/fixes",
            params={"team_id": self.credentials.team_id, "limit": limit},
        )

    def search_fixes(self, q: str, *, limit: int = 20) -> List[Dict[str, Any]]:
        resp = self._request(
            "GET",
            "/api/v1/fixes",
            params={"team_id": self.credentials.team_id, "q": q, "limit": limit},
        )
        return resp.get("items", []) if isinstance(resp, dict) else []

    def push_pending(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._request(
            "POST",
            "/api/v1/pending",
            params={"team_id": self.credentials.team_id},
            json_body={"entries": entries},
        )


# ---------------------------------------------------------------------------
# Fix payload helpers — convert CLI Fix dataclass to wire format
# ---------------------------------------------------------------------------


def fix_to_cloud_payload(fix) -> Dict[str, Any]:
    """Convert a `fixdoc.models.Fix` to the backend's FixCreate schema."""
    return {
        "issue": fix.issue,
        "resolution": fix.resolution,
        "error_excerpt": fix.error_excerpt,
        "tags": fix.tags,
        "notes": fix.notes,
        "author": fix.author,
        "author_email": fix.author_email,
        "is_private": fix.is_private,
        "source_error_ids": fix.source_error_ids,
        "memory_type": fix.memory_type,
        "content_hash": fix.content_hash,
        "client_id": fix.id,
    }


def touch_last_push(creds: CloudCredentials, base_path: Optional[Path] = None) -> None:
    creds.last_push_at = datetime.now(timezone.utc).isoformat()
    save_credentials(creds, base_path=base_path)


def touch_last_pull(creds: CloudCredentials, base_path: Optional[Path] = None) -> None:
    creds.last_pull_at = datetime.now(timezone.utc).isoformat()
    save_credentials(creds, base_path=base_path)


def probe_token(
    api_url: str, token: str, transport: Optional[HttpTransport] = None
) -> Dict[str, Any]:
    """Validate an API token and resolve its team context.

    Returns `{team_id, team_slug, team_name, api_key_name, api_key_id}`.
    Raises `CloudError` on auth failure or network error.
    """
    creds = CloudCredentials(api_url=api_url, token=token)
    client = CloudClient(creds, transport=transport, require_team=False)
    return client.cli_whoami()
