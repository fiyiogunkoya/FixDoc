"""User — Clerk-synced identity."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import created_at, updated_at, uuid_pk


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    clerk_user_id: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(sa.String(320), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(sa.String(128), nullable=False, default="")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
