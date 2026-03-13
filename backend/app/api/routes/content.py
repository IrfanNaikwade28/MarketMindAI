"""
app/api/routes/content.py
--------------------------
Content post endpoints — retrieve and manage generated social media content.

Routes:
  GET  /content                          → list all content posts
  GET  /content/{post_id}                → get a single post
  GET  /content/campaign/{campaign_id}   → all posts for a campaign
  POST /content/generate                 → generate content from a debate state (on-demand)
  PATCH /content/{post_id}/status        → update publish status
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.content_post import ContentPost, PostStatus, Platform
from app.models.debate_session import DebateSession
from app.orchestrator.debate_persistence import load_debate_session
from app.services.content_generator import generate_content, content_to_dict

router = APIRouter(prefix="/content", tags=["content"])


# ── Pydantic schemas ────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: PostStatus


class OnDemandGenerateRequest(BaseModel):
    """Generate content from an existing (completed) debate session."""
    session_id: str
    platforms: list[str] | None = None  # defaults to session's platforms


# ── Helpers ─────────────────────────────────────────────────────

def _post_to_dict(p: ContentPost) -> dict[str, Any]:
    return {
        "id":                        str(p.id),
        "campaign_id":               str(p.campaign_id),
        "debate_session_id":         str(p.debate_session_id) if p.debate_session_id else None,
        "platform":                  p.platform.value,
        "caption":                   p.caption,
        "tweet_text":                p.tweet_text,
        "youtube_title":             p.youtube_title,
        "youtube_description":       p.youtube_description,
        "hashtags":                  p.hashtags or [],
        "image_prompt":              p.image_prompt,
        "call_to_action":            p.call_to_action,
        "predicted_engagement_score": p.predicted_engagement_score,
        "brand_alignment_score":     p.brand_alignment_score,
        "risk_score":                p.risk_score,
        "status":                    p.status.value,
        "scheduled_at":              p.scheduled_at.isoformat() if p.scheduled_at else None,
        "published_at":              p.published_at.isoformat() if p.published_at else None,
        "created_at":                p.created_at.isoformat() if p.created_at else None,
    }


# ── Routes ───────────────────────────────────────────────────────

@router.get("")
async def list_content(
    platform: Platform | None = Query(None),
    status: PostStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all content posts with optional filters."""
    from sqlalchemy import func
    query = select(ContentPost)
    if platform:
        query = query.where(ContentPost.platform == platform)
    if status:
        query = query.where(ContentPost.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = (
        query
        .order_by(ContentPost.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_post_to_dict(p) for p in rows],
    }


@router.get("/campaign/{campaign_id}")
async def get_campaign_content(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get all content posts for a specific campaign."""
    rows = (
        await db.execute(
            select(ContentPost)
            .where(ContentPost.campaign_id == campaign_id)
            .order_by(ContentPost.platform)
        )
    ).scalars().all()

    return {
        "campaign_id": campaign_id,
        "total": len(rows),
        "items": [_post_to_dict(p) for p in rows],
    }


@router.get("/{post_id}")
async def get_content_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a single content post by ID."""
    result = await db.execute(
        select(ContentPost).where(ContentPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Content post not found")
    return _post_to_dict(post)


@router.patch("/{post_id}/status")
async def update_post_status(
    post_id: str,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update the publish status of a content post (draft → scheduled → published)."""
    result = await db.execute(
        select(ContentPost).where(ContentPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Content post not found")

    post.status = body.status

    if body.status == PostStatus.PUBLISHED:
        from datetime import datetime, timezone
        post.published_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(post)
    return _post_to_dict(post)


@router.post("/generate")
async def generate_content_on_demand(
    body: OnDemandGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Re-generate or generate content from an existing completed debate session.
    Useful for re-runs or additional platforms after initial generation.

    Returns generated content (in-memory) without persisting — caller decides
    whether to save via PATCH /content/{id}/status.
    """
    session = await load_debate_session(db, body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")

    if session.status.value not in ("completed",):
        raise HTTPException(
            status_code=400,
            detail=f"Content can only be generated from completed debates (current: {session.status.value})"
        )

    # Reconstruct enough of DebateState from stored snapshot for content gen
    stored_state = session.debate_state or {}

    results = await generate_content(
        state=stored_state,  # type: ignore[arg-type]
        platforms=body.platforms,
    )

    return {
        "session_id": body.session_id,
        "generated": [content_to_dict(r) for r in results],
        "success_count": sum(1 for r in results if r.success),
        "total": len(results),
    }
