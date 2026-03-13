"""
app/models/agent_log.py
-----------------------
Every message an agent produces during a debate is stored here.
This is the raw transcript — used for:
  - Live WebSocket streaming to the frontend
  - Post-debate audit trail
  - Mentor Agent review and learning
  - Analytics on agent behavior over time
"""

import enum
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AgentName(str, enum.Enum):
    TREND      = "trend_agent"
    BRAND      = "brand_agent"
    RISK       = "risk_agent"
    ENGAGEMENT = "engagement_agent"
    CMO        = "cmo_agent"
    MENTOR     = "mentor_agent"


class AgentAction(str, enum.Enum):
    PROPOSE    = "propose"      # Agent puts forward an idea
    CRITIQUE   = "critique"     # Agent challenges another's idea
    SUPPORT    = "support"      # Agent agrees and endorses
    REVISE     = "revise"       # Agent updates its own proposal
    DECIDE     = "decide"       # CMO makes the final call
    REVIEW     = "review"       # Mentor evaluates the outcome
    WARN       = "warn"         # Risk Agent raises a flag


class AgentLog(BaseModel):
    __tablename__ = "agent_logs"

    # ── Parent debate ──────────────────────────────────────────
    debate_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("debate_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Which agent spoke ──────────────────────────────────────
    agent_name: Mapped[AgentName] = mapped_column(
        SAEnum(AgentName), nullable=False, index=True
    )
    action: Mapped[AgentAction] = mapped_column(
        SAEnum(AgentAction), nullable=False
    )

    # ── Content of the agent's message ────────────────────────
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Full structured JSON output from the agent ────────────
    # e.g. {"trend": "...", "confidence": 0.9, "hashtags": [...]}
    structured_output: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)

    # ── Confidence / risk scores ───────────────────────────────
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Position in the debate sequence ───────────────────────
    sequence_order: Mapped[int] = mapped_column(nullable=False, default=0)

    # ── Token usage (for cost tracking) ───────────────────────
    tokens_used: Mapped[int | None] = mapped_column(nullable=True)

    # ── Relationship ───────────────────────────────────────────
    debate_session: Mapped["DebateSession"] = relationship(  # noqa: F821
        "DebateSession", back_populates="agent_logs"
    )

    def __repr__(self) -> str:
        return f"<AgentLog {self.agent_name} → {self.action} (seq={self.sequence_order})>"
