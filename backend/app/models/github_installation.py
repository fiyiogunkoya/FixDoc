"""GitHubInstallation — maps GitHub App installation IDs to teams."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import created_at, uuid_fk, uuid_pk


class GitHubInstallation(Base):
    __tablename__ = "github_installations"

    id: Mapped[uuid.UUID] = uuid_pk()
    installation_id: Mapped[int] = mapped_column(
        sa.BigInteger, unique=True, nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = uuid_fk("teams.id", ondelete="CASCADE")
    # JSON instead of JSONB for cross-dialect portability; PG still stores efficiently
    repositories: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    installed_at: Mapped[datetime] = created_at()
