"""
app/models/content_post.py
--------------------------
Generated social media content produced after a debate is approved.
One ContentPost per platform per campaign run.

Stores:
  - Platform-specific text (caption, tweet, title)
  - Hashtags list
  - Image generation prompt (for DALL-E / Stable Diffusion later)
  - Publish status and scheduled time
"""

import enum
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.models.base import BaseModel


class Platform(str, enum.Enum):
    INSTAGRAM = "instagram"
    TWITTER   = "twitter"
    YOUTUBE   = "youtube"
    LINKEDIN  = "linkedin"
    FACEBOOK  = "facebook"
    TIKTOK    = "tiktok"


class PostStatus(str, enum.Enum):
    DRAFT       = "draft"
    SCHEDULED   = "scheduled"
    PUBLISHED   = "published"
    FAILED      = "failed"
    REJECTED    = "rejected"


class ContentPost(BaseModel):
    __tablename__ = "content_posts"

    # ── Parent references ──────────────────────────────────────
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    debate_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("debate_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Platform ───────────────────────────────────────────────
    platform: Mapped[Platform] = mapped_column(
        SAEnum(Platform), nullable=False, index=True
    )

    # ── Generated content ──────────────────────────────────────
    caption: Mapped[str] = mapped_column(Text, nullable=True)      # Instagram / Facebook
    tweet_text: Mapped[str] = mapped_column(String(280), nullable=True)  # Twitter/X
    youtube_title: Mapped[str] = mapped_column(String(100), nullable=True)
    youtube_description: Mapped[str] = mapped_column(Text, nullable=True)

    # ── Shared content ─────────────────────────────────────────
    hashtags: Mapped[list] = mapped_column(JSON, nullable=True, default=list)
    image_prompt: Mapped[str] = mapped_column(Text, nullable=True)  # AI image gen prompt
    call_to_action: Mapped[str] = mapped_column(String(255), nullable=True)

    # ── Agent scores attached to this post ────────────────────
    predicted_engagement_score: Mapped[float | None] = mapped_column(nullable=True)
    brand_alignment_score: Mapped[float | None] = mapped_column(nullable=True)
    risk_score: Mapped[float | None] = mapped_column(nullable=True)

    # ── Publish lifecycle ──────────────────────────────────────
    status: Mapped[PostStatus] = mapped_column(
        SAEnum(PostStatus), default=PostStatus.DRAFT, nullable=False, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────
    campaign: Mapped["Campaign"] = relationship(          # noqa: F821
        "Campaign", back_populates="content_posts"
    )
    debate_session: Mapped["DebateSession | None"] = relationship(  # noqa: F821
        "DebateSession", back_populates="content_posts"
    )
    analytics: Mapped[list["Analytics"]] = relationship( # noqa: F821
        "Analytics", back_populates="content_post", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ContentPost {self.platform} [{self.status}]>"
