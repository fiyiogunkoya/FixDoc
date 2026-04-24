"""Project — container for fixes/pending/outcomes within a team."""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import created_at, uuid_fk, uuid_pk


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (sa.UniqueConstraint("team_id", "slug", name="uq_project_team_slug"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = uuid_fk("teams.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    git_remote_url: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    created_by_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="RESTRICT")
    created_at: Mapped[datetime] = created_at()
