"""Team schemas."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    created_at: datetime


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    team_id: uuid.UUID
    role: str
    joined_at: datetime


class TeamInvite(BaseModel):
    email: EmailStr
    role: str = Field("member", pattern=r"^(owner|member)$")


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    last_used_at: Optional[datetime] = None
    created_at: datetime


class ApiKeyWithToken(ApiKeyResponse):
    token: str  # only returned on creation, never again
