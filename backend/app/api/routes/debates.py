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
from loguru import logger
from pydantic import BaseModel
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
    create_debate_session,
    finalize_debate_session,
)
from app.orchestrator.debate_state import build_initial_state
from app.orchestrator.debate_engine import DebateOrchestrator


# ── Request bodies ────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    post_text: str  # The (possibly human-edited) Bluesky post text


class RejectRequest(BaseModel):
    feedback: str = ""  # Human feedback explaining why the post was rejected


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


# ── Human approval gate ──────────────────────────────────────────

@router.post("/{session_id}/approve")
async def approve_and_publish(
    session_id: str,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Human approval: publish the (optionally edited) Bluesky post.

    Expects the debate to be in a 'pending_approval' state (i.e. the
    debate engine has generated content and is waiting for human sign-off).
    Publishes the given post_text to Bluesky and updates the session record.
    """
    from app.services.bluesky_service import publish_to_bluesky
    from datetime import datetime, timezone
    import base64 as _b64

    session = await load_debate_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")

    post_text = body.post_text.strip()
    if not post_text:
        raise HTTPException(status_code=422, detail="post_text cannot be empty")

    # ── Decode pre-generated image from stored state ─────────────
    stored_state: dict = session.debate_state or {}
    pending: dict = stored_state.get("pending_approval", {})

    image_bytes: bytes | None = None
    image_b64_stored: str = pending.get("image_b64", "")

    if image_b64_stored:
        try:
            image_bytes = _b64.b64decode(image_b64_stored)
            logger.info("approve | decoded pre-generated image ({} bytes) from state", len(image_bytes))
        except Exception as decode_err:
            logger.warning("approve | failed to decode stored image_b64: {} — text-only", decode_err)
    else:
        logger.warning("approve | no image_b64 in stored state — publishing text-only")

    # ── Publish to Bluesky (with or without image) ───────────────
    result = await publish_to_bluesky(post_text, image_bytes=image_bytes)

    # Persist the result back into the session's debate_state snapshot
    stored_state["bluesky_result"] = {
        "success":      result.success,
        "uri":          result.uri,
        "cid":          result.cid,
        "web_url":      result.web_url,
        "text":         result.text,
        "published_at": result.published_at,
        "error":        result.error,
    }
    stored_state["human_decision"] = "approved"
    stored_state["human_decided_at"] = datetime.now(timezone.utc).isoformat()

    # SQLAlchemy won't detect an in-place dict mutation on a JSON column —
    # we must reassign the attribute to trigger change tracking.
    session.debate_state = stored_state

    await db.commit()

    if not result.success:
        raise HTTPException(
            status_code=502,
            detail=f"Bluesky publish failed: {result.error}",
        )

    return {
        "message":      "Post published to Bluesky",
        "session_id":   session_id,
        "web_url":      result.web_url,
        "uri":          result.uri,
        "text":         result.text,
        "published_at": result.published_at,
    }


@router.post("/{session_id}/reject")
async def reject_post(
    session_id: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Human rejection with feedback.

    Workflow:
      1. Record the rejection + feedback in DB.
      2. Restore the debate state from the stored snapshot.
      3. Inject human feedback into the history as a 'user' turn.
      4. Re-run ONLY the content generation stage (_stage_content) to get
         a fresh draft post without running the full 6-agent debate again.
      5. Return the new draft_post so the frontend can show the approval
         modal again immediately.
    """
    from datetime import datetime, timezone
    from app.services.bluesky_service import build_bluesky_post
    from app.services.content_generator import generate_content, content_to_dict
    from app.services.image_service import generate_image, pick_best_image_prompt
    from app.orchestrator.debate_state import DebateState
    import base64 as _b64

    # 1. Load session from DB
    session = await load_debate_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")

    # 2. Extract stored state snapshot and conversation history
    stored_state: dict = dict(session.debate_state or {})
    history: list = list(stored_state.get("history", []))

    # Record the rejection + feedback in the history so the LLM gets context
    if body.feedback and body.feedback.strip():
        history.append({
            "role":    "user",
            "content": f"[Human Reviewer Feedback]: {body.feedback.strip()}",
        })

    # Update rejection metadata in stored state
    stored_state["human_decision"]   = "rejected"
    stored_state["human_feedback"]   = body.feedback.strip()
    stored_state["human_decided_at"] = datetime.now(timezone.utc).isoformat()

    # Build the re-run state (reuses all campaign context + agent outputs from the debate)
    rerun_state: dict = {
        **stored_state,
        "session_id":        session_id,
        "history":           history,
        "status":            "in_progress",
        "current_stage":     "",
        "websocket_queue":   [],
        "generated_content": [],
        "bluesky_result":    {},
        "pending_approval":  {},
    }

    # 3. Re-run only content generation
    try:
        results      = await generate_content(rerun_state)  # type: ignore[arg-type]
        content_dicts = [content_to_dict(r) for r in results]
        rerun_state["generated_content"] = content_dicts

        new_draft = await build_bluesky_post(content_dicts, state=rerun_state)  # type: ignore[arg-type]

        # ── Regenerate image for the new draft ───────────────────
        new_image_b64: str = ""
        image_prompt: str = pick_best_image_prompt(content_dicts)
        if image_prompt:
            image_bytes = await generate_image(image_prompt)
            if image_bytes:
                new_image_b64 = _b64.b64encode(image_bytes).decode("ascii")
                logger.info("reject | new image generated ({} bytes)", len(image_bytes))
            else:
                logger.warning("reject | image regeneration failed — no preview image")

        rerun_state["pending_approval"] = {
            "draft_post":        new_draft,
            "generated_content": content_dicts,
            "image_b64":         new_image_b64,
            "image_prompt":      image_prompt,
        }

        # 4. Persist updated state
        stored_state.update({
            "generated_content": content_dicts,
            "pending_approval":  rerun_state["pending_approval"],
            "human_decision":    "pending",          # reset for next review
        })
        session.debate_state = stored_state
        await db.commit()

        return {
            "message":    "Content regenerated — new draft ready for review",
            "session_id": session_id,
            "draft_post": new_draft,
            "image_b64":  new_image_b64,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Content regeneration failed: {e}",
        )


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

    state: dict | None = None

    try:
        from app.database.session import AsyncSessionLocal
        from app.models.debate_session import DebateStatus

        # ── Single DB session for the entire WS lifecycle ────────
        # SQLite allows only one writer at a time; opening multiple
        # sequential sessions risks "database is locked" errors.
        # We open one session, do all three DB operations in it,
        # and commit once at the very end.
        async with AsyncSessionLocal() as db:

            # 1. Load campaign
            result = await db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()

            if not campaign:
                await websocket.send_json({"type": "error", "message": "Campaign not found"})
                await websocket.close()
                return

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

            # 2. Create DebateSession row
            db_session = await create_debate_session(
                db=db,
                campaign_id=campaign_id,
                topic=campaign.title,
            )
            state["session_id"] = str(db_session.id)
            db_session.status = DebateStatus.IN_PROGRESS
            await db.flush()   # write the row; don't commit yet

            # Send session_id so frontend can call /approve and /reject later
            await websocket.send_json({
                "type":       "session_created",
                "session_id": state["session_id"],
            })

            # 3. Run debate (streams WS events; no DB writes inside)
            orchestrator = DebateOrchestrator()
            async for event in orchestrator.run_stream(state):
                await websocket.send_json(event)

            # 4. Finalize — persist pending_approval + outcome to DB
            await finalize_debate_session(
                db=db,
                session_id=state["session_id"],
                state=state,
            )
            await db.commit()   # single commit for the whole WS session

        await websocket.close()

    except WebSocketDisconnect:
        # Best-effort save if we have a session_id
        if state and state.get("session_id"):
            try:
                from app.database.session import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    await finalize_debate_session(db=db, session_id=state["session_id"], state=state)
                    await db.commit()
            except Exception:
                pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except Exception:
            pass
