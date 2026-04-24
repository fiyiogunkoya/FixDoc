"""Analyze endpoint — engine reuse + PR gating."""
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
