"""GitHub App plumbing — JWT mint, webhook signature, PR comment upsert."""
import hashlib
import hmac

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.integrations.github_app import (
    mint_app_jwt,
    upsert_pr_comment,
    verify_webhook_signature,
)


@pytest.fixture(scope="module")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


class TestMintAppJwt:
    def test_signs_with_issuer_and_expiry(self, rsa_keypair):
        private, public = rsa_keypair
        token = mint_app_jwt("12345", private)
        claims = jwt.decode(token, public, algorithms=["RS256"])
        assert claims["iss"] == "12345"
        assert claims["exp"] > claims["iat"]
        assert (claims["exp"] - claims["iat"]) <= 9 * 60 + 60  # <= 10 min with skew

    def test_invalid_key_raises(self):
        with pytest.raises(Exception):
            mint_app_jwt("id", "not a key")


class TestVerifyWebhookSignature:
    def test_valid_signature(self):
        body = b'{"event":"ping"}'
        secret = "supersecret"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(body, sig, secret) is True

    def test_tampered_body_fails(self):
        secret = "supersecret"
        sig = "sha256=" + hmac.new(secret.encode(), b'{"event":"ping"}', hashlib.sha256).hexdigest()
        assert verify_webhook_signature(b'{"event":"other"}', sig, secret) is False

    def test_missing_sig_fails(self):
        assert verify_webhook_signature(b"x", None, "s") is False

    def test_empty_secret_fails(self):
        assert verify_webhook_signature(b"x", "sha256=deadbeef", "") is False

    def test_wrong_prefix_fails(self):
        assert verify_webhook_signature(b"x", "md5=deadbeef", "s") is False


class TestUpsertPrComment:
    """Uses httpx.MockTransport to avoid real network."""

    def _client_with_responses(self, handler):
        transport = httpx.MockTransport(handler)
        return httpx.Client(transport=transport)

    def test_creates_new_comment_when_marker_absent(self):
        calls = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append((req.method, str(req.url)))
            if req.method == "GET" and "/comments" in str(req.url):
                return httpx.Response(200, json=[{"id": 99, "body": "something else"}])
            if req.method == "POST" and "/comments" in str(req.url):
                return httpx.Response(201, json={"id": 42, "body": req.content.decode()})
            return httpx.Response(404)

        with self._client_with_responses(handler) as client:
            cid = upsert_pr_comment(
                "tok",
                "owner",
                "repo",
                7,
                "body",
                "<!-- marker -->",
                client=client,
            )

        assert cid == 42
        methods = [m for m, _ in calls]
        assert methods == ["GET", "POST"]

    def test_updates_existing_comment_when_marker_found(self):
        marker = "<!-- marker -->"

        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {"id": 100, "body": "other"},
                        {"id": 200, "body": f"{marker}\nold body"},
                    ],
                )
            if req.method == "PATCH":
                return httpx.Response(200, json={"id": 200})
            return httpx.Response(500)

        with self._client_with_responses(handler) as client:
            cid = upsert_pr_comment(
                "tok", "owner", "repo", 7, "new", marker, client=client
            )
        assert cid == 200
