"""
app/models/base.py
------------------
Shared mixin that every ORM model inherits.
Provides:
  - UUID primary key (no sequential integers — safe for distributed systems)
  - created_at / updated_at auto-timestamps
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class TimestampMixin:
    """Adds created_at and updated_at to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """Adds a UUID primary key stored as a 36-char string (cross-DB safe)."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )


class BaseModel(UUIDMixin, TimestampMixin, Base):
    """
    Abstract base — inherit this in every model.
    Provides id, created_at, updated_at automatically.
    """
    __abstract__ = True
