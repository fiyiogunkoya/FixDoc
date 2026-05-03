"""GitHub App plumbing.

Responsibilities:
  1. Mint a short-lived App JWT from the App ID + RSA private key.
  2. Exchange the App JWT for an installation access token (1 hour lifetime).
  3. Post/update PR comments idempotently via a sentinel HTML marker.
  4. Verify incoming webhook signatures.

We avoid `pygithub` / `githubkit` on purpose — a single App needs maybe 4
HTTP calls in its entire lifetime, and the extra dep adds ~30MB to the image.
Plain httpx + pyjwt is enough and easy to audit.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

import httpx
import jwt

from app.config import Settings

GITHUB_API = "https://api.github.com"


def _normalize_pem(pem: str) -> str:
    """Accept the PEM in any of three forms:

      1. Multi-line PEM with real newlines (paste via Railway's Raw Editor).
      2. Single-line PEM with literal `\\n` escapes (some CI serializers).
      3. Base64-encoded single-line PEM (when Railway's form field truncates
         multi-line values at the first newline). Encode locally with:
             base64 < private-key.pem | tr -d '\\n' | pbcopy
         and paste the result.

    We sniff which form was pasted and convert all of them to canonical
    real-newline PEM before passing to pyjwt/cryptography.
    """
    import base64
    import binascii

    pem = pem.strip()
    # Strip UTF-8 BOM if a Windows editor added one
    if pem.startswith("﻿"):
        pem = pem[1:]

    # Form 3: no BEGIN marker → assume base64-wrapped PEM
    if "-----BEGIN" not in pem:
        try:
            decoded = base64.b64decode(pem, validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return pem  # not base64; let pyjwt raise its own error
        if "-----BEGIN" in decoded:
            pem = decoded.strip()

    # Form 2: literal `\n` characters and no real newlines → unescape
    if "\\n" in pem and "\n" not in pem:
        pem = pem.replace("\\n", "\n")

    return pem


def mint_app_jwt(app_id: str, private_key_pem: str) -> str:
    """Create a 10-minute App JWT signed with the App's RSA private key."""
    now = int(time.time())
    payload = {
        "iat": now - 30,  # GitHub tolerates 30s clock skew; pre-date to avoid drift
        "exp": now + 9 * 60,  # max 10 min; 9 keeps margin
        "iss": app_id,
    }
    return jwt.encode(payload, _normalize_pem(private_key_pem), algorithm="RS256")


def installation_token(
    app_id: str,
    private_key_pem: str,
    installation_id: int,
    *,
    client: Optional[httpx.Client] = None,
) -> str:
    """Exchange an App JWT for an installation access token."""
    app_jwt = mint_app_jwt(app_id, private_key_pem)
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"

    owned_client = client is None
    if client is None:
        client = httpx.Client(timeout=15)
    try:
        resp = client.post(url, headers=headers)
        resp.raise_for_status()
        return resp.json()["token"]
    finally:
        if owned_client:
            client.close()


def verify_webhook_signature(payload: bytes, signature: Optional[str], secret: str) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature header `X-Hub-Signature-256`.

    GitHub sends `sha256=<hex_digest>`. Empty/missing secret short-circuits to
    False so unauthenticated webhooks can never sneak through in prod.
    """
    if not secret or not signature:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.split("=", 1)[1])


def _find_existing_comment(
    token: str,
    owner: str,
    repo: str,
    pr_number: int,
    marker: str,
    *,
    client: httpx.Client,
) -> Optional[int]:
    """Scan PR comments for the FixDoc sentinel marker; return comment_id if found."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    resp = client.get(url, headers=headers)
    resp.raise_for_status()
    for comment in resp.json():
        if marker in (comment.get("body") or ""):
            return comment["id"]
    return None


def upsert_pr_comment(
    token: str,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    marker: str,
    *,
    client: Optional[httpx.Client] = None,
) -> int:
    """Post a new PR comment, or update the existing marker-tagged comment.

    Returns the GitHub comment ID. Callers can log it for audit/debugging but
    don't need to track it across runs — the marker is the source of truth.
    """
    owned_client = client is None
    if client is None:
        client = httpx.Client(timeout=20)
    try:
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        existing_id = _find_existing_comment(
            token, owner, repo, pr_number, marker, client=client
        )
        if existing_id is not None:
            resp = client.patch(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{existing_id}",
                headers=headers,
                json={"body": body},
            )
            resp.raise_for_status()
            return existing_id

        resp = client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=headers,
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()["id"]
    finally:
        if owned_client:
            client.close()


def get_installation_token_for_settings(
    settings: Settings, installation_id: int
) -> str:
    """Convenience wrapper — raises if App credentials are not configured."""
    if not settings.github_app_id or not settings.github_app_private_key:
        raise RuntimeError(
            "GitHub App not configured — set FIXDOC_GITHUB_APP_ID and "
            "FIXDOC_GITHUB_APP_PRIVATE_KEY"
        )
    return installation_token(
        settings.github_app_id, settings.github_app_private_key, installation_id
    )
