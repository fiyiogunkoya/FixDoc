"""Team CRUD + membership helpers."""
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.team import Team, TeamMember
from app.models.user import User


def create_team(db: Session, *, owner: User, name: str, slug: str) -> Team:
    team = Team(name=name, slug=slug, owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    db.commit()
    db.refresh(team)
    return team


def list_teams_for_user(db: Session, *, user_id: uuid.UUID) -> List[Team]:
    return (
        db.query(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == user_id)
        .order_by(Team.created_at.desc())
        .all()
    )


def get_team(db: Session, *, team_id: uuid.UUID) -> Optional[Team]:
    return db.query(Team).filter(Team.id == team_id).one_or_none()


def get_team_by_slug(db: Session, *, slug: str) -> Optional[Team]:
    return db.query(Team).filter(Team.slug == slug).one_or_none()


def list_members(db: Session, *, team_id: uuid.UUID) -> List[TeamMember]:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id).all()


def add_member(
    db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, role: str = "member"
) -> TeamMember:
    existing = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .one_or_none()
    )
    if existing is not None:
        return existing
    member = TeamMember(team_id=team_id, user_id=user_id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member
