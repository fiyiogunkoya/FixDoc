"""ApiKey — hashed token for CLI authentication."""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import created_at, uuid_fk, uuid_pk


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = uuid_fk("teams.id", ondelete="CASCADE")
    created_by_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="RESTRICT")
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    hashed_token: Mapped[str] = mapped_column(
        sa.String(128), unique=True, nullable=False, index=True
    )
    prefix: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
