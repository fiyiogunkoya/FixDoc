"""Fix schemas — mirror fixdoc.models.Fix for the wire format."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FixBase(BaseModel):
    issue: str
    resolution: str
    error_excerpt: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    author: Optional[str] = None
    author_email: Optional[str] = None
    is_private: bool = False
    source_error_ids: Optional[List[str]] = None
    memory_type: str = "fix"


class FixCreate(FixBase):
    project_id: Optional[uuid.UUID] = None
    client_id: Optional[str] = None  # CLI-side UUID for idempotent push
    content_hash: Optional[str] = None  # precomputed by CLI; backend recomputes if missing


class FixUpdate(BaseModel):
    issue: Optional[str] = None
    resolution: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    is_private: Optional[bool] = None


class FixResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    created_by_id: uuid.UUID
    content_hash: str
    issue: str
    resolution: str
    error_excerpt: Optional[str]
    tags: Optional[List[str]] = None
    notes: Optional[str]
    author: Optional[str]
    author_email: Optional[str]
    is_private: bool
    source_error_ids: Optional[List[str]]
    applied_count: int
    success_count: int
    last_applied_at: Optional[datetime]
    memory_type: str
    created_at: datetime
    updated_at: datetime


class FixBulkCreate(BaseModel):
    fixes: List[FixCreate] = Field(..., max_length=500)
    project_id: Optional[uuid.UUID] = None


class FixBulkResult(BaseModel):
    created: int
    duplicates: int
    ids: List[uuid.UUID]


class FixSearchParams(BaseModel):
    q: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    limit: int = 50
    offset: int = 0
