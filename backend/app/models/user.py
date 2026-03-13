"""
app/models/user.py
------------------
User account model.
Supports JWT-based auth (password stored as bcrypt hash).
One user can own many campaigns.
"""

import enum
from sqlalchemy import String, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserRole(str, enum.Enum):
    ADMIN   = "admin"
    MANAGER = "manager"
    VIEWER  = "viewer"


class User(BaseModel):
    __tablename__ = "users"

    # ── Identity ───────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)

    # ── Auth ───────────────────────────────────────────────────
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Role ───────────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole), default=UserRole.MANAGER, nullable=False
    )

    # ── Brand context (used by Brand Agent) ───────────────────
    brand_name: Mapped[str]    = mapped_column(String(255), nullable=True)
    brand_voice: Mapped[str]   = mapped_column(String(500), nullable=True)
    target_audience: Mapped[str] = mapped_column(String(500), nullable=True)

    # ── Relationships ──────────────────────────────────────────
    campaigns: Mapped[list["Campaign"]] = relationship(  # noqa: F821
        "Campaign", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"
