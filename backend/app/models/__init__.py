"""
app/models/__init__.py
----------------------
Central import point for all ORM models.

Import order matters — models with FKs must be imported
after the models they reference so SQLAlchemy resolves
relationships correctly at startup.
"""

from app.models.base import BaseModel, TimestampMixin, UUIDMixin  # noqa: F401
from app.models.user import User, UserRole                         # noqa: F401
from app.models.campaign import Campaign, CampaignStatus, CampaignGoal  # noqa: F401
from app.models.debate_session import (                            # noqa: F401
    DebateSession,
    DebateStatus,
    DebateOutcome,
)
from app.models.agent_log import AgentLog, AgentName, AgentAction  # noqa: F401
from app.models.content_post import ContentPost, Platform, PostStatus  # noqa: F401
from app.models.analytics import Analytics, AnalyticsWindow        # noqa: F401

__all__ = [
    # Base
    "BaseModel",
    "TimestampMixin",
    "UUIDMixin",
    # User
    "User",
    "UserRole",
    # Campaign
    "Campaign",
    "CampaignStatus",
    "CampaignGoal",
    # Debate
    "DebateSession",
    "DebateStatus",
    "DebateOutcome",
    # Agent
    "AgentLog",
    "AgentName",
    "AgentAction",
    # Content
    "ContentPost",
    "Platform",
    "PostStatus",
    # Analytics
    "Analytics",
    "AnalyticsWindow",
]
