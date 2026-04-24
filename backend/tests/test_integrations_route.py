"""Integrations binding — link + unlink + conflict protection."""
import uuid

from fastapi.testclient import TestClient

from app.models.github_installation import GitHubInstallation
from app.models.team import Team, TeamMember
from app.models.user import User


def _make_team(client: TestClient, slug: str) -> str:
    return client.post("/api/v1/teams", json={"name": "T", "slug": slug}).json()["id"]


def test_link_and_list_installation(client: TestClient):
    team_id = _make_team(client, "gh-1")
    resp = client.post(
        f"/api/v1/integrations/github?team_id={team_id}",
        json={"installation_id": 100001},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["installation_id"] == 100001

    resp = client.get(f"/api/v1/integrations/github?team_id={team_id}")
    assert resp.status_code == 200
    assert any(i["installation_id"] == 100001 for i in resp.json())


def test_relink_same_team_is_idempotent(client: TestClient):
    team_id = _make_team(client, "gh-2")
    for _ in range(2):
        resp = client.post(
            f"/api/v1/integrations/github?team_id={team_id}",
            json={"installation_id": 200002},
        )
        assert resp.status_code == 200
    resp = client.get(f"/api/v1/integrations/github?team_id={team_id}")
    assert len([i for i in resp.json() if i["installation_id"] == 200002]) == 1


def test_unlink_removes_installation(client: TestClient):
    team_id = _make_team(client, "gh-3")
    client.post(
        f"/api/v1/integrations/github?team_id={team_id}",
        json={"installation_id": 300003},
    )
    resp = client.delete(
        f"/api/v1/integrations/github/300003?team_id={team_id}"
    )
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/integrations/github?team_id={team_id}")
    assert resp.json() == []


def test_cannot_steal_installation_from_another_team(client: TestClient, db):
    # Create a team via API (this is the caller's team)
    my_team = _make_team(client, "gh-mine")

    # Create a separate team manually + stash an install under it
    other_user = User(
        clerk_user_id="user_other",
        email="other@example.com",
        display_name="Other",
    )
    db.add(other_user)
    db.flush()
    other_team = Team(name="Other", slug="gh-other", owner_id=other_user.id)
    db.add(other_team)
    db.flush()
    db.add(TeamMember(team_id=other_team.id, user_id=other_user.id, role="owner"))
    db.add(
        GitHubInstallation(
            installation_id=987654, team_id=other_team.id, repositories=[]
        )
    )
    db.commit()

    # Attempt to link the other team's install to my team
    resp = client.post(
        f"/api/v1/integrations/github?team_id={my_team}",
        json={"installation_id": 987654},
    )
    assert resp.status_code == 409
