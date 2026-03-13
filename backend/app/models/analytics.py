"""
app/models/analytics.py
-----------------------
Tracks performance metrics for each ContentPost after publishing.

One Analytics row = one snapshot in time for one post.
Multiple snapshots can be stored over a post's lifetime
(e.g. 1h, 24h, 7d, 30d after publish).

Also stores brand-level health metrics (sentiment, share-of-voice)
that are aggregated at the campaign level by the analytics service.
"""

import enum
from sqlalchemy import String, Float, Integer, ForeignKey, Enum as SAEnum, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.models.base import BaseModel


class AnalyticsWindow(str, enum.Enum):
    ONE_HOUR   = "1h"
    SIX_HOURS  = "6h"
    ONE_DAY    = "24h"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"


class Analytics(BaseModel):
    __tablename__ = "analytics"

    # ── Parent references ──────────────────────────────────────
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_post_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("content_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Measurement window ─────────────────────────────────────
    window: Mapped[AnalyticsWindow] = mapped_column(
        SAEnum(AnalyticsWindow), nullable=False, default=AnalyticsWindow.ONE_DAY
    )
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Engagement metrics ─────────────────────────────────────
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reach: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Computed rates ─────────────────────────────────────────
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    click_through_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    conversion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Brand health metrics ───────────────────────────────────
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)   # -1.0 to 1.0
    brand_mention_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_of_voice: Mapped[float | None] = mapped_column(Float, nullable=True)    # % vs competitors

    # ── Trend metrics ──────────────────────────────────────────
    hashtag_reach: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)
    # e.g. {"#ai": 50000, "#marketing": 120000}

    # ── Agent prediction vs actual (for Mentor Agent learning) ─
    predicted_engagement: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_engagement: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Raw platform data dump ─────────────────────────────────
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)

    # ── Relationships ──────────────────────────────────────────
    campaign: Mapped["Campaign"] = relationship(      # noqa: F821
        "Campaign", back_populates="analytics"
    )
    content_post: Mapped["ContentPost | None"] = relationship(  # noqa: F821
        "ContentPost", back_populates="analytics"
    )

    def __repr__(self) -> str:
        return (
            f"<Analytics campaign={self.campaign_id} "
            f"window={self.window} engagement={self.engagement_rate:.2%}>"
        )
