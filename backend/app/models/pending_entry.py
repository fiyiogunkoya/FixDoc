"""PendingEntry — mirrors fixdoc.pending.PendingEntry + team/project context."""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import created_at, updated_at, uuid_fk, uuid_pk


class PendingEntry(Base):
    __tablename__ = "pending_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = uuid_fk("teams.id", ondelete="CASCADE")
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="RESTRICT")

    error_id: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    error_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    short_message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    error_excerpt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tags: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    deferred_at: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    resource_address: Mapped[Optional[str]] = mapped_column(sa.String(256), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    file: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    command: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    cwd: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True, index=True)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="pending")
    command_family: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    kind: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    worthiness: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="memory_worthy"
    )

    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
