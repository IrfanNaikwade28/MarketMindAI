"""
app/api/routes/analytics.py
-----------------------------
Analytics & engagement metrics endpoints.

Routes:
  GET  /analytics                          → list analytics records
  GET  /analytics/summary                  → aggregated totals across all campaigns
  GET  /analytics/bluesky                  → bluesky-wide totals (no DB needed)
  GET  /analytics/top-content              → top performing content posts
  GET  /analytics/agent-stats              → per-agent call/approval counts from agent_logs
  GET  /analytics/campaign/{campaign_id}   → aggregated stats for a campaign
  GET  /analytics/bluesky/{uri}            → fetch live Bluesky engagement for a post
  POST /analytics/bluesky/sync             → sync Bluesky metrics into DB for a content post
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.analytics import Analytics, AnalyticsWindow
from app.models.content_post import ContentPost
from app.models.agent_log import AgentLog, AgentName, AgentAction
from app.services.bluesky_service import get_engagement

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ── Pydantic schemas ────────────────────────────────────────────

class BlueskySyncRequest(BaseModel):
    """Sync Bluesky engagement metrics into the DB for a ContentPost."""
    post_id: str        # UUID of the ContentPost row
    bluesky_uri: str    # AT URI returned at publish time


# ── Helpers ─────────────────────────────────────────────────────

def _analytics_to_dict(a: Analytics) -> dict[str, Any]:
    return {
        "id":                       str(a.id),
        "campaign_id":              str(a.campaign_id) if a.campaign_id else None,
        "content_post_id":          str(a.content_post_id) if a.content_post_id else None,
        "window":                   a.window.value if a.window else None,
        "impressions":              a.impressions,
        "reach":                    a.reach,
        "likes":                    a.likes,
        "comments":                 a.comments,
        "shares":                   a.shares,
        "clicks":                   a.clicks,
        "engagement_rate":          a.engagement_rate,
        "sentiment_score":          a.sentiment_score,
        "prediction_accuracy":      a.prediction_accuracy,
        "measured_at":              a.measured_at.isoformat() if a.measured_at else None,
        "created_at":               a.created_at.isoformat() if a.created_at else None,
    }


# ── Routes ───────────────────────────────────────────────────────

@router.get("")
async def list_analytics(
    campaign_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List analytics records with optional campaign filter."""
    query = select(Analytics)
    if campaign_id:
        query = query.where(Analytics.campaign_id == campaign_id)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = (
        query
        .order_by(Analytics.measured_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_analytics_to_dict(a) for a in rows],
    }


@router.get("/summary")
async def get_summary(
    window: str = Query("day", description="Aggregation window: day | week | month"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregated totals across all analytics records."""
    rows = (await db.execute(select(Analytics))).scalars().all()

    if not rows:
        return {
            "total_records": 0,
            "totals": {"impressions": 0, "reach": 0, "likes": 0, "comments": 0, "shares": 0, "clicks": 0},
            "averages": {"engagement_rate": 0, "sentiment_score": 0},
        }

    n = len(rows)
    return {
        "total_records": n,
        "window": window,
        "totals": {
            "impressions": sum(r.impressions or 0 for r in rows),
            "reach":       sum(r.reach       or 0 for r in rows),
            "likes":       sum(r.likes       or 0 for r in rows),
            "comments":    sum(r.comments    or 0 for r in rows),
            "shares":      sum(r.shares      or 0 for r in rows),
            "clicks":      sum(r.clicks      or 0 for r in rows),
        },
        "averages": {
            "engagement_rate": round(sum(r.engagement_rate or 0 for r in rows) / n, 4),
            "sentiment_score": round(sum(r.sentiment_score or 0 for r in rows) / n, 4),
        },
    }


@router.get("/bluesky")
async def get_bluesky_summary(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Bluesky-wide engagement totals pulled from the Analytics table
    (rows that came from Bluesky sync).  Returns zeros when DB is empty.
    """
    rows = (await db.execute(select(Analytics))).scalars().all()

    total_likes    = sum(r.likes    or 0 for r in rows)
    total_comments = sum(r.comments or 0 for r in rows)
    total_shares   = sum(r.shares   or 0 for r in rows)

    # Count published posts (any platform — Bluesky publishes via debate engine)
    from app.models.content_post import PostStatus
    published = (await db.execute(
        select(func.count(ContentPost.id)).where(
            ContentPost.status == PostStatus.PUBLISHED,
        )
    )).scalar_one()

    return {
        "total_posts":   published,
        "total_likes":   total_likes,
        "total_reposts": total_shares,
        "total_replies": total_comments,
    }


@router.get("/top-content")
async def get_top_content(
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return top performing content posts by engagement rate."""
    rows = (
        await db.execute(
            select(Analytics)
            .order_by(Analytics.engagement_rate.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {"items": [_analytics_to_dict(r) for r in rows]}


@router.get("/agent-stats")
async def get_agent_stats(
    window: str = Query("day", description="Unused for now — kept for API compatibility"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Per-agent call counts and approval rates from the AgentLog table.
    Returns a dict keyed by agent name: { total_calls, approved, rejected, avg_confidence }
    """
    rows = (await db.execute(select(AgentLog))).scalars().all()

    stats: dict[str, dict] = {}
    for row in rows:
        name = row.agent_name.value if hasattr(row.agent_name, "value") else str(row.agent_name)
        if name not in stats:
            stats[name] = {"total_calls": 0, "approved": 0, "rejected": 0, "confidence_sum": 0.0, "confidence_count": 0}

        stats[name]["total_calls"] += 1

        action = row.action.value if hasattr(row.action, "value") else str(row.action)
        if "approv" in action.lower():
            stats[name]["approved"] += 1
        elif "reject" in action.lower():
            stats[name]["rejected"] += 1

        if row.confidence_score is not None:
            stats[name]["confidence_sum"]   += float(row.confidence_score)
            stats[name]["confidence_count"] += 1

    # Clean up internal accumulators
    result = {}
    for name, s in stats.items():
        result[name] = {
            "total_calls":    s["total_calls"],
            "approved":       s["approved"],
            "rejected":       s["rejected"],
            "avg_confidence": round(s["confidence_sum"] / s["confidence_count"], 3)
                              if s["confidence_count"] else None,
        }

    return result


@router.get("/campaign/{campaign_id}")
async def get_campaign_analytics(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Aggregated engagement stats for a campaign across all its content posts.
    Returns totals and averages in a single response.
    """
    rows = (
        await db.execute(
            select(Analytics).where(Analytics.campaign_id == campaign_id)
        )
    ).scalars().all()

    if not rows:
        return {
            "campaign_id": campaign_id,
            "total_records": 0,
            "totals": {},
            "averages": {},
        }

    n = len(rows)
    totals = {
        "impressions": sum(r.impressions or 0 for r in rows),
        "reach":       sum(r.reach       or 0 for r in rows),
        "likes":       sum(r.likes       or 0 for r in rows),
        "comments":    sum(r.comments    or 0 for r in rows),
        "shares":      sum(r.shares      or 0 for r in rows),
        "clicks":      sum(r.clicks      or 0 for r in rows),
    }
    averages = {
        "engagement_rate":     round(sum(r.engagement_rate     or 0 for r in rows) / n, 4),
        "sentiment_score":     round(sum(r.sentiment_score     or 0 for r in rows) / n, 4),
        "prediction_accuracy": round(sum(r.prediction_accuracy or 0 for r in rows) / n, 4),
    }

    return {
        "campaign_id":   campaign_id,
        "total_records": n,
        "totals":        totals,
        "averages":      averages,
        "records":       [_analytics_to_dict(r) for r in rows],
    }


@router.get("/bluesky/{uri:path}")
async def get_bluesky_engagement(uri: str) -> dict[str, Any]:
    """
    Fetch live engagement metrics from Bluesky for a published post.
    URL-encode the AT URI when calling from a browser.
    """
    decoded_uri = unquote(uri)
    result = await get_engagement(decoded_uri)
    return {
        "success":      result.success,
        "uri":          result.uri,
        "like_count":   result.like_count,
        "reply_count":  result.reply_count,
        "repost_count": result.repost_count,
        "quote_count":  result.quote_count,
        "fetched_at":   result.fetched_at,
        "error":        result.error,
    }


@router.post("/bluesky/sync")
async def sync_bluesky_metrics(
    body: BlueskySyncRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Pull live Bluesky engagement for a post and upsert into the Analytics table.
    """
    result = await db.execute(
        select(ContentPost).where(ContentPost.id == body.post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="ContentPost not found")

    engagement = await get_engagement(body.bluesky_uri)
    if not engagement.success:
        raise HTTPException(
            status_code=502,
            detail=f"Bluesky API error: {engagement.error}"
        )

    existing = (
        await db.execute(
            select(Analytics).where(Analytics.content_post_id == body.post_id)
        )
    ).scalar_one_or_none()

    from datetime import datetime, timezone

    if existing:
        existing.likes       = engagement.like_count
        existing.comments    = engagement.reply_count
        existing.shares      = engagement.repost_count
        existing.measured_at = datetime.now(timezone.utc)
    else:
        total_interactions = (
            engagement.like_count
            + engagement.reply_count
            + engagement.repost_count
            + engagement.quote_count
        )
        new_record = Analytics(
            campaign_id=post.campaign_id,
            content_post_id=post.id,
            window=AnalyticsWindow.ONE_DAY,
            likes=engagement.like_count,
            comments=engagement.reply_count,
            shares=engagement.repost_count,
            engagement_rate=round(total_interactions / max(1, 100), 4),
            measured_at=datetime.now(timezone.utc),
        )
        db.add(new_record)
        existing = new_record

    await db.commit()
    await db.refresh(existing)
    return {
        "message":   "Bluesky metrics synced",
        "analytics": _analytics_to_dict(existing),
    }
