"""Analyze endpoint — engine reuse + PR gating."""
from unittest.mock import patch

from fastapi.testclient import TestClient


def _make_team(client: TestClient) -> str:
    return client.post("/api/v1/teams", json={"name": "T", "slug": "analyze-t"}).json()["id"]


def _minimal_plan():
    """Smallest Terraform plan that runs through the engine without error."""
    return {
        "format_version": "1.2",
        "terraform_version": "1.5.0",
        "planned_values": {"root_module": {"resources": []}},
        "resource_changes": [
            {
                "address": "aws_s3_bucket.example",
                "type": "aws_s3_bucket",
                "name": "example",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"bucket": "my-bucket"},
                },
            }
        ],
    }


def test_analyze_returns_score_and_markdown(client: TestClient):
    team_id = _make_team(client)
    resp = client.post(
        f"/api/v1/analyze?team_id={team_id}",
        json={"plan": _minimal_plan()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "score" in body and 0 <= body["score"] <= 100
    assert body["severity"] in {"low", "medium", "high", "critical"}
    assert "Terraform Risk Analysis" in body["markdown"]
    assert body["plan_fingerprint"]  # non-empty


def test_analyze_rejects_pr_block_without_installation(client: TestClient):
    team_id = _make_team(client)
    resp = client.post(
        f"/api/v1/analyze?team_id={team_id}",
        json={
            "plan": _minimal_plan(),
            "pr": {
                "installation_id": 99999,
                "owner": "acme",
                "repo": "infra",
                "pull_number": 1,
            },
        },
    )
    assert resp.status_code == 403
    assert "not linked" in resp.text.lower()


def test_analyze_empty_plan_still_scores(client: TestClient):
    team_id = _make_team(client)
    resp = client.post(
        f"/api/v1/analyze?team_id={team_id}",
        json={"plan": {"resource_changes": []}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["score"] == 0


def test_analyze_pr_comment_failure_returns_200_with_error(client: TestClient, db):
    """PR-comment failures must NOT 5xx — Cloudflare replaces 5xx response
    bodies with bare templates that hide the actual cause. We surface the
    failure as a string in the 200 response body instead."""
    import uuid
    from app.models.github_installation import GitHubInstallation

    team_id = _make_team(client)
    db.add(
        GitHubInstallation(
            installation_id=12345,
            team_id=uuid.UUID(team_id),
            repositories=[],
        )
    )
    db.commit()

    # Make get_installation_token_for_settings blow up — covers the same
    # surface as a real GitHub auth failure or a malformed App private key.
    with patch(
        "app.routers.analyze.get_installation_token_for_settings",
        side_effect=RuntimeError("token mint failed: bad RSA key"),
    ):
        resp = client.post(
            f"/api/v1/analyze?team_id={team_id}",
            json={
                "plan": _minimal_plan(),
                "pr": {
                    "installation_id": 12345,
                    "owner": "acme",
                    "repo": "infra",
                    "pull_number": 1,
                },
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Engine result still present
    assert "score" in body
    assert body["pr_comment_id"] is None
    # Error surfaced as string in body
    assert "RuntimeError" in body["pr_comment_error"]
    assert "bad RSA key" in body["pr_comment_error"]
