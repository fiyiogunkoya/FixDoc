"""Fix CRUD + bulk + dedup."""
from fastapi.testclient import TestClient


def _make_team(client: TestClient, slug: str = "t1") -> str:
    resp = client.post("/api/v1/teams", json={"name": "T", "slug": slug})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_create_and_get_fix(client: TestClient):
    team_id = _make_team(client)
    payload = {
        "issue": "S3 bucket already exists",
        "resolution": "Add a random suffix to the bucket name",
    }
    resp = client.post(f"/api/v1/fixes?team_id={team_id}", json=payload)
    assert resp.status_code == 201, resp.text
    fix = resp.json()
    assert fix["content_hash"], "content hash auto-computed"

    resp = client.get(f"/api/v1/fixes/{fix['id']}?team_id={team_id}")
    assert resp.status_code == 200
    assert resp.json()["issue"] == payload["issue"]


def test_bulk_push_dedups_by_content_hash(client: TestClient):
    team_id = _make_team(client, "t2")
    items = [
        {"issue": "Same issue", "resolution": "Same fix"},
        {"issue": "Same issue", "resolution": "Same fix"},  # dup
        {"issue": "Different", "resolution": "Unique"},
    ]
    resp = client.post(
        f"/api/v1/fixes/bulk?team_id={team_id}",
        json={"fixes": items},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["duplicates"] == 1


def test_list_fixes_filters_by_team(client: TestClient):
    team_id = _make_team(client, "t3")
    client.post(
        f"/api/v1/fixes?team_id={team_id}",
        json={"issue": "A", "resolution": "B"},
    )
    resp = client.get(f"/api/v1/fixes?team_id={team_id}")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_search_ilike(client: TestClient):
    team_id = _make_team(client, "t4")
    client.post(
        f"/api/v1/fixes?team_id={team_id}",
        json={"issue": "BucketAlreadyExists error", "resolution": "suffix"},
    )
    resp = client.get(f"/api/v1/fixes?team_id={team_id}&q=Bucket")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("Bucket" in i["issue"] for i in items)
