"""Team CRUD + membership."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user, require_team_member
from app.models.user import User
from app.schemas.team import TeamCreate, TeamMemberResponse, TeamResponse
from app.services import team_service

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.get("", response_model=List[TeamResponse])
def list_teams(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return team_service.list_teams_for_user(db, user_id=user.id)


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if team_service.get_team_by_slug(db, slug=payload.slug) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already taken")
    return team_service.create_team(db, owner=user, name=payload.name, slug=payload.slug)


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(
    team_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_member(team_id=str(team_id), user=user, db=db)
    team = team_service.get_team(db, team_id=team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return team


@router.get("/{team_id}/members", response_model=List[TeamMemberResponse])
def list_team_members(
    team_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_member(team_id=str(team_id), user=user, db=db)
    return team_service.list_members(db, team_id=team_id)
