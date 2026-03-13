"""
app/models/debate_session.py
----------------------------
One DebateSession is created per campaign run.
It tracks the full lifecycle of the multi-agent debate:
  Trend → Brand → Risk → Engagement → CMO → (optional Mentor review)

The `debate_state` JSON field stores the live LangGraph state
so the session can be resumed or replayed.
"""

import enum
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class DebateStatus(str, enum.Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    FAILED     = "failed"
    VETOED     = "vetoed"     # CMO or Risk Agent rejected all proposals


class DebateOutcome(str, enum.Enum):
    APPROVED          = "approved"
    APPROVED_MODIFIED = "approved_modified"
    REJECTED          = "rejected"
    NEEDS_REVISION    = "needs_revision"


class DebateSession(BaseModel):
    __tablename__ = "debate_sessions"

    # ── Campaign FK ────────────────────────────────────────────
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Lifecycle ──────────────────────────────────────────────
    status: Mapped[DebateStatus] = mapped_column(
        SAEnum(DebateStatus), default=DebateStatus.PENDING, nullable=False, index=True
    )
    outcome: Mapped[DebateOutcome | None] = mapped_column(
        SAEnum(DebateOutcome), nullable=True
    )

    # ── Debate metadata ────────────────────────────────────────
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=True)

    # ── Full LangGraph state snapshot (JSON) ───────────────────
    # Stores each agent's proposal, votes, and the final CMO decision
    debate_state: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)

    # ── CMO final decision summary ─────────────────────────────
    cmo_decision: Mapped[str] = mapped_column(Text, nullable=True)
    mentor_feedback: Mapped[str] = mapped_column(Text, nullable=True)

    # ── Error info if debate failed ────────────────────────────
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────
    campaign: Mapped["Campaign"] = relationship(     # noqa: F821
        "Campaign", back_populates="debate_sessions"
    )
    agent_logs: Mapped[list["AgentLog"]] = relationship(  # noqa: F821
        "AgentLog", back_populates="debate_session", cascade="all, delete-orphan"
    )
    content_posts: Mapped[list["ContentPost"]] = relationship(  # noqa: F821
        "ContentPost", back_populates="debate_session"
    )

    def __repr__(self) -> str:
        return f"<DebateSession campaign={self.campaign_id} [{self.status}]>"
