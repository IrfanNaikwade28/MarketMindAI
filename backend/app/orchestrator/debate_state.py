"""
app/orchestrator/debate_state.py
---------------------------------
Typed state schema for the debate engine.

DebateState is a TypedDict that flows through every stage of the
orchestrator. It carries:
  - Campaign context (inputs)
  - Each agent's raw AgentResponse (as dict for JSON serializability)
  - The assembled history for multi-turn LLM context
  - Lifecycle flags (status, errors, timestamps)

Using a TypedDict (instead of a Pydantic model) keeps it lightweight
and directly JSON-serializable for storage in DebateSession.debate_state.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict


class AgentOutputDict(TypedDict, total=False):
    """Serialized form of AgentResponse stored in state."""
    agent_name: str
    action: str
    message: str
    structured_output: dict[str, Any]
    confidence_score: float
    risk_score: float
    engagement_score: float
    tokens_used: int
    success: bool
    error: str | None


class DebateState(TypedDict, total=False):
    """
    Full mutable state that passes through every debate stage.

    Inputs (set before debate starts):
        session_id       : UUID of the DebateSession row
        campaign_id      : UUID of the parent Campaign row
        campaign_title   : str
        campaign_goal    : str
        brand_name       : str
        brand_voice      : str
        target_audience  : str
        brand_guidelines : str
        keywords         : list[str]
        platforms        : list[str]

    Agent outputs (populated as each stage runs):
        trend_agent_output      : AgentOutputDict
        brand_agent_output      : AgentOutputDict
        risk_agent_output       : AgentOutputDict
        engagement_agent_output : AgentOutputDict
        cmo_agent_output        : AgentOutputDict
        mentor_agent_output     : AgentOutputDict

    Debate history (accumulated for multi-turn LLM context):
        history          : list of {"role": ..., "content": ...}

    Lifecycle:
        status           : pending | in_progress | completed | failed | vetoed
        outcome          : approved | approved_modified | rejected | needs_revision
        current_stage    : which agent is currently running
        sequence_counter : monotonically increasing order per log entry
        error            : error message if something failed
        started_at       : ISO timestamp
        completed_at     : ISO timestamp
        websocket_queue  : list of messages to stream to frontend (in-memory only)
    """

    # ── Identifiers ────────────────────────────────────────────
    session_id: str
    campaign_id: str

    # ── Campaign context ───────────────────────────────────────
    campaign_title: str
    campaign_goal: str
    brand_name: str
    brand_voice: str
    target_audience: str
    brand_guidelines: str
    keywords: list[str]
    platforms: list[str]

    # ── Agent outputs ──────────────────────────────────────────
    trend_agent_output: AgentOutputDict
    brand_agent_output: AgentOutputDict
    risk_agent_output: AgentOutputDict
    engagement_agent_output: AgentOutputDict
    cmo_agent_output: AgentOutputDict
    mentor_agent_output: AgentOutputDict

    # ── LLM conversation history ───────────────────────────────
    history: list[dict[str, str]]

    # ── Lifecycle ──────────────────────────────────────────────
    status: str
    outcome: str
    current_stage: str
    sequence_counter: int
    error: str | None
    started_at: str
    completed_at: str | None

    # ── WebSocket streaming queue ──────────────────────────────
    websocket_queue: list[dict[str, Any]]

    # ── Generated content (populated post-debate if approved) ──
    generated_content: list[dict[str, Any]]

    # ── Bluesky publish result ─────────────────────────────────
    bluesky_result: dict[str, Any]


def build_initial_state(
    campaign_id: str,
    session_id: str,
    campaign_title: str,
    campaign_goal: str,
    brand_name: str,
    brand_voice: str,
    target_audience: str,
    brand_guidelines: str,
    keywords: list[str],
    platforms: list[str],
) -> DebateState:
    """
    Factory function that creates a fresh DebateState
    with all required campaign context fields pre-populated.
    """
    return DebateState(
        session_id=session_id,
        campaign_id=campaign_id,
        campaign_title=campaign_title,
        campaign_goal=campaign_goal,
        brand_name=brand_name,
        brand_voice=brand_voice,
        target_audience=target_audience,
        brand_guidelines=brand_guidelines,
        keywords=keywords,
        platforms=platforms,
        history=[],
        status="pending",
        outcome="",
        current_stage="",
        sequence_counter=0,
        error=None,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
        websocket_queue=[],
        generated_content=[],
        bluesky_result={},
    )
