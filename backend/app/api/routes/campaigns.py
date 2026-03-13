"""
app/api/routes/campaigns.py
----------------------------
Campaign CRUD endpoints.

Routes:
  POST   /campaigns              → create a campaign
  GET    /campaigns              → list all campaigns (paginated)
  GET    /campaigns/{id}         → get single campaign
  PATCH  /campaigns/{id}         → update campaign fields
  DELETE /campaigns/{id}         → soft-delete (archive) campaign
  POST   /campaigns/{id}/run     → trigger a debate + content generation run
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.campaign import Campaign, CampaignStatus, CampaignGoal
from app.orchestrator.debate_state import build_initial_state

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ── Pydantic schemas ────────────────────────────────────────────

class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str | None = None
    goal: CampaignGoal = CampaignGoal.BRAND_AWARENESS
    target_audience: str | None = None
    brand_guidelines: str | None = None
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["instagram", "twitter"])
    # Brand context (used by agents)
    brand_name: str = Field(..., min_length=1, max_length=200)
    brand_voice: str | None = "professional and engaging"
    # owner_id is a placeholder — Phase 9 will add real auth
    owner_id: str | None = None


class CampaignUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    goal: CampaignGoal | None = None
    target_audience: str | None = None
    brand_guidelines: str | None = None
    keywords: list[str] | None = None
    platforms: list[str] | None = None
    brand_name: str | None = None
    brand_voice: str | None = None
    status: CampaignStatus | None = None


class CampaignOut(BaseModel):
    id: str
    title: str
    description: str | None
    goal: str
    target_audience: str | None
    brand_guidelines: str | None
    keywords: list
    platforms: list
    status: str
    owner_id: str

    model_config = {"from_attributes": True}


# ── Helpers ─────────────────────────────────────────────────────

def _campaign_to_dict(c: Campaign) -> dict[str, Any]:
    return {
        "id":               str(c.id),
        "title":            c.title,
        "description":      c.description,
        "goal":             c.goal.value,
        "target_audience":  c.target_audience,
        "brand_name":       getattr(c, "brand_name", None),
        "brand_guidelines": c.brand_guidelines,
        "keywords":         c.keywords or [],
        "platforms":        c.platforms or [],
        "status":           c.status.value,
        "owner_id":         str(c.owner_id),
        "created_at":       c.created_at.isoformat() if c.created_at else None,
        "updated_at":       c.updated_at.isoformat() if c.updated_at else None,
    }


def _get_system_owner_id(db_hint: AsyncSession) -> str:
    """Temporary: return a fixed UUID as owner until auth is implemented."""
    return "00000000-0000-0000-0000-000000000001"


# ── Routes ───────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new campaign."""
    owner_id = body.owner_id or _get_system_owner_id(db)

    campaign = Campaign(
        title=body.title,
        description=body.description,
        goal=body.goal,
        target_audience=body.target_audience,
        brand_guidelines=body.brand_guidelines,
        keywords=body.keywords,
        platforms=body.platforms,
        owner_id=owner_id,
        status=CampaignStatus.DRAFT,
        brand_name=body.brand_name,
    )

    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _campaign_to_dict(campaign)


@router.get("")
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: CampaignStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List campaigns with optional status filter and pagination."""
    query = select(Campaign)
    if status:
        query = query.where(Campaign.status == status)

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(query)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_campaign_to_dict(c) for c in rows],
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fetch a single campaign by UUID."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_to_dict(campaign)


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Partial update on a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)
    return _campaign_to_dict(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def archive_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete by archiving a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = CampaignStatus.ARCHIVED
    await db.commit()


@router.post("/{campaign_id}/run", status_code=202)
async def run_campaign(
    campaign_id: str,
    brand_name: str = Query(..., description="Brand name for agent context"),
    brand_voice: str = Query("professional and engaging", description="Brand voice/tone"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Trigger a full debate + content generation + Bluesky publish run.

    Dispatches to a Celery worker — returns immediately with a task_id
    so the caller can poll GET /campaigns/{id}/task/{task_id} for status.

    Falls back to FastAPI BackgroundTasks if Redis/Celery is not available
    (graceful degradation for local dev without Redis running).
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == CampaignStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="Cannot run an archived campaign")

    # Mark as debating immediately so the UI reflects the change
    campaign.status = CampaignStatus.DEBATING
    await db.commit()

    # Build the initial debate state (serialisable dict for Celery)
    state = build_initial_state(
        campaign_id=str(campaign.id),
        session_id=str(uuid.uuid4()),   # overwritten by persistence layer
        campaign_title=campaign.title,
        campaign_goal=campaign.goal.value,
        brand_name=brand_name,
        brand_voice=brand_voice,
        target_audience=campaign.target_audience or "",
        brand_guidelines=campaign.brand_guidelines or "",
        keywords=campaign.keywords or [],
        platforms=campaign.platforms or ["instagram", "twitter"],
    )

    # ── Dispatch to Celery ──────────────────────────────────────
    # Remove the websocket_queue (contains non-serialisable state)
    # and bluesky_result before sending to Celery (Celery uses JSON)
    state_for_celery = {
        k: v for k, v in state.items()
        if k not in ("websocket_queue",)
    }

    task_id: str | None = None
    try:
        from app.workers.tasks import run_debate_task
        task = run_debate_task.apply_async(
            args=[campaign_id, state_for_celery],
            queue="debates",
        )
        task_id = task.id
    except Exception as celery_err:
        # Celery/Redis not available — fall back to in-process background task
        from loguru import logger
        logger.warning(
            "Celery unavailable ({}), falling back to in-process background run.",
            celery_err
        )
        import asyncio
        from app.orchestrator.debate_persistence import run_debate_with_persistence

        async def _fallback_run() -> None:
            from app.database.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                try:
                    _, final_state = await run_debate_with_persistence(
                        db=bg_db, campaign_id=campaign_id, state=state
                    )
                    outcome = final_state.get("outcome", "")
                    debate_status = final_state.get("status", "")
                    if outcome in ("approved", "approved_modified"):
                        new_status = CampaignStatus.APPROVED
                    elif debate_status in ("vetoed", "failed"):
                        new_status = CampaignStatus.DRAFT   # let user revise & retry
                    else:
                        new_status = CampaignStatus.DRAFT
                    res = await bg_db.execute(
                        select(Campaign).where(Campaign.id == campaign_id)
                    )
                    c = res.scalar_one_or_none()
                    if c:
                        c.status = new_status
                        await bg_db.commit()
                        logger.info(
                            "Background debate done | campaign={} | outcome={} | new_status={}",
                            campaign_id, outcome, new_status.value
                        )
                except Exception as e:
                    logger.error("Fallback debate run failed: {}", e)
                    import traceback; traceback.print_exc()

        asyncio.create_task(_fallback_run())

    return {
        "message":     "Debate started",
        "campaign_id": campaign_id,
        "session_id":  state["session_id"],
        "task_id":     task_id,
        "mode":        "celery" if task_id else "background",
        "status":      "debating",
    }
