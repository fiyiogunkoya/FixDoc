"""Fix — mirrors fixdoc.models.Fix fields + team/project context."""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import created_at, updated_at, uuid_fk, uuid_pk


class Fix(Base):
    __tablename__ = "fixes"
    __table_args__ = (
        sa.UniqueConstraint("team_id", "content_hash", name="uq_fix_team_content_hash"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = uuid_fk("teams.id", ondelete="CASCADE")
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="RESTRICT")

    content_hash: Mapped[str] = mapped_column(sa.String(16), nullable=False, index=True)
    issue: Mapped[str] = mapped_column(sa.Text, nullable=False)
    resolution: Mapped[str] = mapped_column(sa.Text, nullable=False)
    error_excerpt: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    # JSON for cross-dialect compatibility; Postgres stores as JSONB efficiently
    tags: Mapped[Optional[list]] = mapped_column(sa.JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(sa.String(128), nullable=True)
    author_email: Mapped[Optional[str]] = mapped_column(sa.String(320), nullable=True)
    is_private: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    source_error_ids: Mapped[Optional[list]] = mapped_column(sa.JSON, nullable=True)
    applied_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_applied_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    memory_type: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="fix")

    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
