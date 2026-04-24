"""PendingEntry schemas."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PendingEntryBase(BaseModel):
    error_id: str
    error_type: str
    short_message: str
    error_excerpt: str
    tags: str = ""
    deferred_at: str
    resource_address: Optional[str] = None
    error_code: Optional[str] = None
    file: Optional[str] = None
    command: Optional[str] = None
    cwd: Optional[str] = None
    session_id: Optional[str] = None
    status: str = "pending"
    command_family: Optional[str] = None
    kind: Optional[str] = None
    worthiness: str = "memory_worthy"


class PendingEntryCreate(PendingEntryBase):
    project_id: Optional[uuid.UUID] = None


class PendingEntryResponse(PendingEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PendingBulkCreate(BaseModel):
    entries: List[PendingEntryCreate] = Field(..., max_length=500)
    project_id: Optional[uuid.UUID] = None
