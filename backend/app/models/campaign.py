"""
app/models/campaign.py
----------------------
A Campaign is the top-level unit of work.
It belongs to a User, triggers a DebateSession,
and produces one or more ContentPosts.
"""

import enum
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class CampaignStatus(str, enum.Enum):
    DRAFT      = "draft"
    DEBATING   = "debating"
    APPROVED   = "approved"
    GENERATING = "generating"
    PUBLISHED  = "published"
    ARCHIVED   = "archived"


class CampaignGoal(str, enum.Enum):
    BRAND_AWARENESS    = "brand_awareness"
    LEAD_GENERATION    = "lead_generation"
    PRODUCT_LAUNCH     = "product_launch"
    ENGAGEMENT         = "engagement"
    RETENTION          = "retention"
    TREND_RIDING       = "trend_riding"
    SALES              = "sales"
    COMMUNITY_BUILDING = "community_building"
    THOUGHT_LEADERSHIP = "thought_leadership"


class Campaign(BaseModel):
    __tablename__ = "campaigns"

    # ── Core fields ────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    brand_name: Mapped[str] = mapped_column(String(255), nullable=True)  # persisted brand name

    # ── Strategy inputs ────────────────────────────────────────
    goal: Mapped[CampaignGoal] = mapped_column(
        SAEnum(CampaignGoal), nullable=False, default=CampaignGoal.BRAND_AWARENESS
    )
    target_audience: Mapped[str] = mapped_column(String(500), nullable=True)
    brand_guidelines: Mapped[str] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, nullable=True, default=list)

    # ── Target platforms (e.g. ["instagram", "twitter", "youtube"]) ──
    platforms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # ── Lifecycle ──────────────────────────────────────────────
    status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus), default=CampaignStatus.DRAFT, nullable=False, index=True
    )

    # ── Owner FK ───────────────────────────────────────────────
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # ── Relationships ──────────────────────────────────────────
    owner: Mapped["User"] = relationship(           # noqa: F821
        "User", back_populates="campaigns"
    )
    debate_sessions: Mapped[list["DebateSession"]] = relationship(  # noqa: F821
        "DebateSession", back_populates="campaign", cascade="all, delete-orphan"
    )
    content_posts: Mapped[list["ContentPost"]] = relationship(      # noqa: F821
        "ContentPost", back_populates="campaign", cascade="all, delete-orphan"
    )
    analytics: Mapped[list["Analytics"]] = relationship(            # noqa: F821
        "Analytics", back_populates="campaign", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Campaign '{self.title}' [{self.status}]>"
