"""Team creation + listing."""
from fastapi.testclient import TestClient


def test_create_and_list_team(client: TestClient):
    resp = client.post("/api/v1/teams", json={"name": "Platform", "slug": "platform"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Platform"
    assert body["slug"] == "platform"

    resp = client.get("/api/v1/teams")
    assert resp.status_code == 200
    teams = resp.json()
    assert any(t["slug"] == "platform" for t in teams)


def test_slug_must_be_unique(client: TestClient):
    client.post("/api/v1/teams", json={"name": "A", "slug": "dup"})
    resp = client.post("/api/v1/teams", json={"name": "B", "slug": "dup"})
    assert resp.status_code == 409


def test_slug_format_validation(client: TestClient):
    resp = client.post("/api/v1/teams", json={"name": "Bad", "slug": "BAD SLUG"})
    assert resp.status_code == 422
