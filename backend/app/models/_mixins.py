"""Shared column helpers — cross-dialect so SQLite tests work too."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def uuid_fk(target: str, **kwargs) -> Mapped[uuid.UUID]:
    return mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey(target, **kwargs), nullable=False)


def created_at() -> Mapped[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def updated_at() -> Mapped[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
