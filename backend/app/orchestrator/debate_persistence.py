"""
app/orchestrator/debate_persistence.py
---------------------------------------
Handles all database reads/writes for the debate lifecycle.

Responsibilities:
  - Create a DebateSession row when a debate starts
  - Save each AgentLog row as agents complete their turns
  - Update DebateSession status/outcome when debate finishes
  - Load a past debate session for replay or review

This module is the bridge between the stateless debate_engine
and the PostgreSQL database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.debate_session import DebateSession, DebateStatus, DebateOutcome
from app.models.agent_log import AgentLog, AgentName, AgentAction
from app.orchestrator.debate_state import DebateState
from app.agents.base_agent import AgentResponse


# ── Session creation ────────────────────────────────────────────

async def create_debate_session(
    db: AsyncSession,
    campaign_id: str,
    topic: str,
) -> DebateSession:
    """
    Insert a new DebateSession row with PENDING status.
    Returns the saved session with its generated UUID.
    """
    session = DebateSession(
        campaign_id=campaign_id,
        status=DebateStatus.PENDING,
        topic=topic,
        debate_state={},
    )
    db.add(session)
    await db.flush()  # flush to get the generated UUID without committing
    logger.info("DebateSession created | id={} | campaign={}", session.id, campaign_id)
    return session


# ── Log a single agent turn ─────────────────────────────────────

async def save_agent_log(
    db: AsyncSession,
    debate_session_id: str,
    response: AgentResponse,
    sequence_order: int,
) -> AgentLog:
    """
    Persist one agent's response as an AgentLog row.
    Called after each stage completes.
    """
    log = AgentLog(
        debate_session_id=debate_session_id,
        agent_name=response.agent_name,
        action=response.action,
        message=response.message,
        structured_output=response.structured_output,
        confidence_score=response.confidence_score,
        risk_score=response.risk_score,
        engagement_score=response.engagement_score,
        tokens_used=response.tokens_used,
        sequence_order=sequence_order,
    )
    db.add(log)
    await db.flush()
    logger.debug(
        "AgentLog saved | agent={} | action={} | seq={}",
        response.agent_name.value, response.action.value, sequence_order
    )
    return log


# ── Update session state snapshot ───────────────────────────────

async def update_debate_state_snapshot(
    db: AsyncSession,
    session_id: str,
    state: DebateState,
) -> None:
    """
    Overwrite the debate_state JSON column with the current state snapshot.
    Called after each stage so the debate is resumable.
    """
    result = await db.execute(
        select(DebateSession).where(DebateSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        logger.warning("DebateSession {} not found for state update", session_id)
        return

    # Store state without websocket_queue (not serializable / not needed in DB)
    storable_state = {k: v for k, v in state.items() if k != "websocket_queue"}
    session.debate_state = storable_state
    session.status = DebateStatus(state.get("status", "in_progress"))
    await db.flush()


# ── Finalize session ────────────────────────────────────────────

async def finalize_debate_session(
    db: AsyncSession,
    session_id: str,
    state: DebateState,
) -> DebateSession:
    """
    Mark the DebateSession as completed/failed/vetoed.
    Write the CMO decision and mentor feedback.
    Returns the updated session.
    """
    result = await db.execute(
        select(DebateSession).where(DebateSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise ValueError(f"DebateSession {session_id} not found")

    # Map state status → DB enum
    status_map = {
        "completed": DebateStatus.COMPLETED,
        "failed":    DebateStatus.FAILED,
        "vetoed":    DebateStatus.VETOED,
    }
    session.status = status_map.get(state.get("status", "failed"), DebateStatus.FAILED)

    # Map outcome → DB enum
    outcome_map = {
        "approved":          DebateOutcome.APPROVED,
        "approved_modified": DebateOutcome.APPROVED_MODIFIED,
        "rejected":          DebateOutcome.REJECTED,
        "needs_revision":    DebateOutcome.NEEDS_REVISION,
    }
    outcome_str = state.get("outcome", "")
    session.outcome = outcome_map.get(outcome_str)

    # CMO summary
    cmo_out = state.get("cmo_agent_output", {})
    session.cmo_decision = (
        cmo_out.get("executive_summary")
        or cmo_out.get("rejection_reason")
        or cmo_out.get("message", "")
    )

    # Mentor feedback
    mentor_out = state.get("mentor_agent_output", {})
    session.mentor_feedback = mentor_out.get("overall_assessment", "")

    # Final state snapshot
    storable = {k: v for k, v in state.items() if k != "websocket_queue"}
    session.debate_state = storable

    await db.flush()
    logger.info(
        "DebateSession finalized | id={} | status={} | outcome={}",
        session_id, session.status, session.outcome
    )
    return session


# ── Load session for replay / API read ──────────────────────────

async def load_debate_session(
    db: AsyncSession,
    session_id: str,
) -> DebateSession | None:
    """Fetch a DebateSession with its related AgentLogs (ordered by sequence)."""
    result = await db.execute(
        select(DebateSession).where(DebateSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def load_agent_logs(
    db: AsyncSession,
    session_id: str,
) -> list[AgentLog]:
    """Return all AgentLogs for a session in sequence order."""
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.debate_session_id == session_id)
        .order_by(AgentLog.sequence_order)
    )
    return list(result.scalars().all())


# ── Full orchestrated run with DB persistence ───────────────────

async def run_debate_with_persistence(
    db: AsyncSession,
    campaign_id: str,
    state: DebateState,
) -> tuple[DebateSession, DebateState]:
    """
    High-level convenience function used by the API and Celery workers.

    1. Creates a DebateSession row
    2. Runs the full debate engine
    3. Saves each AgentLog after every stage
    4. Finalizes and returns session + final state

    Returns:
        (DebateSession, final DebateState)
    """
    from app.orchestrator.debate_engine import DebateOrchestrator

    # 1. Create session
    db_session = await create_debate_session(
        db=db,
        campaign_id=campaign_id,
        topic=state.get("campaign_title", "Campaign"),
    )
    state["session_id"] = str(db_session.id)

    # Update status to in_progress
    db_session.status = DebateStatus.IN_PROGRESS
    await db.flush()

    # 2. Build orchestrator with persistence callback
    log_buffer: list[tuple[AgentResponse, int]] = []

    def on_agent_complete(s: DebateState, response: AgentResponse) -> None:
        """Collect responses — save them after the debate completes."""
        log_buffer.append((response, s.get("sequence_counter", 0)))

    orchestrator = DebateOrchestrator(on_agent_complete=on_agent_complete)

    # 3. Run debate
    final_state = await orchestrator.run(state)

    # 4. Save all agent logs
    for response, seq in log_buffer:
        await save_agent_log(
            db=db,
            debate_session_id=str(db_session.id),
            response=response,
            sequence_order=seq,
        )

    # 5. Finalize session
    final_session = await finalize_debate_session(
        db=db,
        session_id=str(db_session.id),
        state=final_state,
    )

    await db.commit()
    return final_session, final_state
