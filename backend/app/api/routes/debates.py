"""
app/api/routes/debates.py
--------------------------
Debate session endpoints.

Routes:
  GET  /debates                          → list debate sessions
  GET  /debates/{session_id}             → get debate session detail
  GET  /debates/{session_id}/logs        → get all agent logs for a session
  GET  /debates/{session_id}/stream      → WebSocket stream for live debate events
  POST /debates/{session_id}/retry       → retry a failed/vetoed debate
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.debate_session import DebateSession, DebateStatus
from app.models.agent_log import AgentLog
from app.models.campaign import Campaign
from app.orchestrator.debate_persistence import (
    load_debate_session,
    load_agent_logs,
    run_debate_with_persistence,
)
from app.orchestrator.debate_state import build_initial_state
from app.orchestrator.debate_engine import DebateOrchestrator

router = APIRouter(prefix="/debates", tags=["debates"])


# ── Helpers ─────────────────────────────────────────────────────

def _session_to_dict(s: DebateSession) -> dict[str, Any]:
    return {
        "id":              str(s.id),
        "campaign_id":     str(s.campaign_id),
        "status":          s.status.value,
        "outcome":         s.outcome.value if s.outcome else None,
        "round_number":    s.round_number,
        "topic":           s.topic,
        "cmo_decision":    s.cmo_decision,
        "mentor_feedback": s.mentor_feedback,
        "error_message":   s.error_message,
        "created_at":      s.created_at.isoformat() if s.created_at else None,
        "updated_at":      s.updated_at.isoformat() if s.updated_at else None,
    }


def _log_to_dict(log: AgentLog) -> dict[str, Any]:
    return {
        "id":               str(log.id),
        "debate_session_id": str(log.debate_session_id),
        "agent_name":       log.agent_name.value,
        "action":           log.action.value,
        "message":          log.message,
        "structured_output": log.structured_output or {},
        "confidence_score": log.confidence_score,
        "risk_score":       log.risk_score,
        "engagement_score": log.engagement_score,
        "tokens_used":      log.tokens_used,
        "sequence_order":   log.sequence_order,
        "created_at":       log.created_at.isoformat() if log.created_at else None,
    }


# ── Routes ───────────────────────────────────────────────────────

@router.get("")
async def list_debates(
    campaign_id: str | None = Query(None),
    status: DebateStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List debate sessions, optionally filtered by campaign or status."""
    from sqlalchemy import func
    query = select(DebateSession)
    if campaign_id:
        query = query.where(DebateSession.campaign_id == campaign_id)
    if status:
        query = query.where(DebateSession.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = (
        query
        .order_by(DebateSession.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_session_to_dict(s) for s in rows],
    }


@router.get("/{session_id}")
async def get_debate(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get full detail of a single debate session including state snapshot."""
    session = await load_debate_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")

    data = _session_to_dict(session)
    data["debate_state"] = session.debate_state or {}
    return data


@router.get("/{session_id}/logs")
async def get_debate_logs(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get all agent logs for a debate session in sequence order."""
    session = await load_debate_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")

    logs = await load_agent_logs(db, session_id)
    return {
        "session_id": session_id,
        "total_logs": len(logs),
        "logs": [_log_to_dict(log) for log in logs],
    }


@router.post("/{session_id}/retry", status_code=202)
async def retry_debate(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Retry a failed or vetoed debate. Rebuilds state from the stored snapshot
    and kicks off a new debate run.
    """
    session = await load_debate_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")

    if session.status not in (DebateStatus.FAILED, DebateStatus.VETOED):
        raise HTTPException(
            status_code=400,
            detail=f"Only FAILED or VETOED debates can be retried (current: {session.status})"
        )

    # Load the stored state snapshot
    stored_state = session.debate_state or {}

    # Build fresh state from stored context
    new_state = build_initial_state(
        campaign_id=str(session.campaign_id),
        session_id=str(uuid.uuid4()),
        campaign_title=stored_state.get("campaign_title", "Campaign"),
        campaign_goal=stored_state.get("campaign_goal", "brand_awareness"),
        brand_name=stored_state.get("brand_name", ""),
        brand_voice=stored_state.get("brand_voice", "professional"),
        target_audience=stored_state.get("target_audience", ""),
        brand_guidelines=stored_state.get("brand_guidelines", ""),
        keywords=stored_state.get("keywords", []),
        platforms=stored_state.get("platforms", ["instagram", "twitter"]),
    )

    # Run synchronously (could be moved to Celery in Phase 8)
    final_session, _ = await run_debate_with_persistence(
        db=db,
        campaign_id=str(session.campaign_id),
        state=new_state,
    )

    return {
        "message": "Debate retried",
        "new_session_id": str(final_session.id),
        "original_session_id": session_id,
        "status": final_session.status.value,
        "outcome": final_session.outcome.value if final_session.outcome else None,
    }


# ── WebSocket: live debate stream ────────────────────────────────

@router.websocket("/{campaign_id}/stream")
async def debate_stream(
    websocket: WebSocket,
    campaign_id: str,
    brand_name: str = Query(""),
    brand_voice: str = Query("professional and engaging"),
):
    """
    WebSocket endpoint that streams the live debate in real time.

    Connect with:
      ws://localhost:8000/api/v1/debates/{campaign_id}/stream
         ?brand_name=AcmeCo&brand_voice=bold+and+friendly

    Events are JSON objects:
      { "type": "agent_message", "stage": "trend", "agent": "trend",
        "action": "propose", "message": "...", "scores": {...}, ... }
    """
    await websocket.accept()

    try:
        # Load campaign from DB to get context
        from app.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()

        if not campaign:
            await websocket.send_json({"type": "error", "message": "Campaign not found"})
            await websocket.close()
            return

        # Prefer query-param values; fall back to campaign.brand_name, then title
        resolved_brand_name  = brand_name.strip() or getattr(campaign, "brand_name", None) or campaign.title
        resolved_brand_voice = brand_voice.strip() or "professional and engaging"

        state = build_initial_state(
            campaign_id=campaign_id,
            session_id=str(uuid.uuid4()),
            campaign_title=campaign.title,
            campaign_goal=campaign.goal.value,
            brand_name=resolved_brand_name,
            brand_voice=resolved_brand_voice,
            target_audience=campaign.target_audience or "",
            brand_guidelines=campaign.brand_guidelines or "",
            keywords=campaign.keywords or [],
            platforms=campaign.platforms or ["instagram", "twitter"],
        )

        orchestrator = DebateOrchestrator()

        # Stream all events to the WebSocket client
        async for event in orchestrator.run_stream(state):
            await websocket.send_json(event)

        await websocket.close()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except Exception:
            pass
