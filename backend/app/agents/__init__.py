"""
app/agents/__init__.py
----------------------
Exports all agents and the shared AgentResponse dataclass.
The orchestrator imports everything it needs from here.
"""

from app.agents.base_agent import BaseAgent, AgentResponse           # noqa: F401
from app.agents.trend_agent import TrendAgent                        # noqa: F401
from app.agents.brand_agent import BrandAgent                        # noqa: F401
from app.agents.risk_agent import RiskAgent                          # noqa: F401
from app.agents.engagement_agent import EngagementAgent              # noqa: F401
from app.agents.cmo_agent import CMOAgent                            # noqa: F401
from app.agents.mentor_agent import MentorAgent                      # noqa: F401

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "TrendAgent",
    "BrandAgent",
    "RiskAgent",
    "EngagementAgent",
    "CMOAgent",
    "MentorAgent",
]
