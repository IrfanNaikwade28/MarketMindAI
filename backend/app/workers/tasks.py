"""
app/workers/tasks.py
---------------------
All Celery tasks for the AI Council application.

Tasks:
  run_debate_task          — run a full debate + content gen + Bluesky publish
  sync_post_metrics        — pull Bluesky engagement for one post → Analytics row
  sync_all_bluesky_metrics — periodic: sync all published posts (beat job)
  cleanup_stale_debates    — periodic: mark stuck IN_PROGRESS debates as FAILED

Design pattern — async in Celery:
  Celery workers are synchronous. All our core logic (debate engine, DB, Bluesky)
  is async. The bridge: each task calls `asyncio.run(_async_fn(...))`, which
  creates a fresh event loop for that task's lifetime. This is safe because
  each Celery worker process handles one task at a time (prefetch_multiplier=1).

Task states exposed to the API:
  PENDING  → task queued, not yet started
  STARTED  → worker picked up the task (task_track_started=True)
  SUCCESS  → task completed — result stored in Redis
  FAILURE  → task raised an unhandled exception
  RETRY    → task is being retried
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select, update

logger = get_task_logger(__name__)


# ───────────────────────────────────────────────────────────────
# Task 1: run_debate_task
# ───────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.tasks.run_debate_task",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_debate_task(self, campaign_id: str, state_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Run the full debate pipeline for a campaign in the background.

    Steps:
      1. Persist a new DebateSession row.
      2. Run all 6 agent stages via DebateOrchestrator.
      3. Generate platform-specific content (all platforms concurrently).
      4. Publish the best text to Bluesky.
      5. Update Campaign.status based on CMO outcome.
      6. Return a summary dict stored in the Celery result backend.

    Args:
        campaign_id: UUID string of the Campaign row.
        state_dict:  DebateState dict produced by build_initial_state().

    Returns:
        dict with session_id, status, outcome, bluesky_url.
    """
    logger.info("run_debate_task started | campaign=%s | task=%s", campaign_id, self.request.id)
    self.update_state(state="STARTED", meta={"campaign_id": campaign_id, "stage": "init"})

    try:
        result = asyncio.run(_run_debate_async(self, campaign_id, state_dict))
        logger.info("run_debate_task complete | campaign=%s | outcome=%s",
                    campaign_id, result.get("outcome"))
        return result

    except Exception as exc:
        logger.error("run_debate_task failed | campaign=%s | error=%s", campaign_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "campaign_id": campaign_id,
                "status": "failed",
                "error": str(exc),
            }


async def _run_debate_async(task, campaign_id: str, state_dict: dict[str, Any]) -> dict[str, Any]:
    """Async implementation of the debate task."""
    from app.database.session import AsyncSessionLocal
    from app.models.campaign import Campaign, CampaignStatus
    from app.orchestrator.debate_persistence import run_debate_with_persistence

    async with AsyncSessionLocal() as db:
        # Run full debate pipeline (engine → content gen → Bluesky)
        task.update_state(state="STARTED", meta={"stage": "debating", "campaign_id": campaign_id})
        db_session, final_state = await run_debate_with_persistence(
            db=db,
            campaign_id=campaign_id,
            state=state_dict,
        )

        # Update campaign status from debate outcome
        outcome = final_state.get("outcome", "")
        new_status = (
            CampaignStatus.APPROVED
            if outcome in ("approved", "approved_modified")
            else CampaignStatus.DRAFT
        )
        await db.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(status=new_status)
        )
        await db.commit()

        bsky = final_state.get("bluesky_result", {})
        return {
            "campaign_id":  campaign_id,
            "session_id":   str(db_session.id),
            "status":       final_state.get("status", "unknown"),
            "outcome":      outcome,
            "bluesky_url":  bsky.get("web_url", ""),
            "bluesky_uri":  bsky.get("uri", ""),
            "published":    bsky.get("success", False),
            "completed_at": final_state.get("completed_at", ""),
        }


# ───────────────────────────────────────────────────────────────
# Task 2: sync_post_metrics
# ───────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.tasks.sync_post_metrics",
    max_retries=3,
    default_retry_delay=120,
)
def sync_post_metrics(self, post_id: str, bluesky_uri: str) -> dict[str, Any]:
    """
    Pull engagement metrics from Bluesky for a single ContentPost
    and upsert into the Analytics table.

    Args:
        post_id:      UUID of the ContentPost row.
        bluesky_uri:  AT URI of the Bluesky post.

    Returns:
        dict with like_count, reply_count, repost_count, quote_count.
    """
    logger.info("sync_post_metrics | post=%s | uri=%s", post_id, bluesky_uri)
    try:
        return asyncio.run(_sync_post_async(post_id, bluesky_uri))
    except Exception as exc:
        logger.error("sync_post_metrics failed | post=%s | %s", post_id, exc)
        raise self.retry(exc=exc)


async def _sync_post_async(post_id: str, bluesky_uri: str) -> dict[str, Any]:
    """Async implementation of post metrics sync."""
    from app.database.session import AsyncSessionLocal
    from app.models.content_post import ContentPost
    from app.models.analytics import Analytics, AnalyticsWindow
    from app.services.bluesky_service import get_engagement

    engagement = await get_engagement(bluesky_uri)
    if not engagement.success:
        raise RuntimeError(f"Bluesky engagement fetch failed: {engagement.error}")

    async with AsyncSessionLocal() as db:
        # Load the content post to get campaign_id
        post = (await db.execute(
            select(ContentPost).where(ContentPost.id == post_id)
        )).scalar_one_or_none()

        if not post:
            raise ValueError(f"ContentPost {post_id} not found")

        # Upsert analytics row
        existing = (await db.execute(
            select(Analytics).where(Analytics.content_post_id == post_id)
        )).scalar_one_or_none()

        total = (
            engagement.like_count + engagement.reply_count
            + engagement.repost_count + engagement.quote_count
        )
        rate = round(total / max(1, 100), 4)

        if existing:
            existing.likes        = engagement.like_count
            existing.comments     = engagement.reply_count
            existing.shares       = engagement.repost_count
            existing.engagement_rate = rate
            existing.measured_at  = datetime.now(timezone.utc)
        else:
            db.add(Analytics(
                campaign_id=post.campaign_id,
                content_post_id=post.id,
                window=AnalyticsWindow.ONE_DAY,
                likes=engagement.like_count,
                comments=engagement.reply_count,
                shares=engagement.repost_count,
                engagement_rate=rate,
                measured_at=datetime.now(timezone.utc),
            ))

        await db.commit()

    return {
        "post_id":      post_id,
        "bluesky_uri":  bluesky_uri,
        "like_count":   engagement.like_count,
        "reply_count":  engagement.reply_count,
        "repost_count": engagement.repost_count,
        "quote_count":  engagement.quote_count,
        "synced_at":    datetime.now(timezone.utc).isoformat(),
    }


# ───────────────────────────────────────────────────────────────
# Task 3: sync_all_bluesky_metrics  (beat: every 30 min)
# ───────────────────────────────────────────────────────────────

@shared_task(name="app.workers.tasks.sync_all_bluesky_metrics")
def sync_all_bluesky_metrics() -> dict[str, Any]:
    """
    Periodic task (beat): find all ContentPosts that have a Bluesky URI
    stored in their debate session state and queue a sync_post_metrics
    sub-task for each one.

    Looks up the bluesky_uri from the DebateSession.debate_state JSON.
    """
    logger.info("sync_all_bluesky_metrics: scanning published posts")
    return asyncio.run(_sync_all_async())


async def _sync_all_async() -> dict[str, Any]:
    """Async scan: find posts with Bluesky URIs and enqueue sync tasks."""
    from app.database.session import AsyncSessionLocal
    from app.models.debate_session import DebateSession, DebateStatus
    from app.models.content_post import ContentPost, PostStatus

    queued = 0
    async with AsyncSessionLocal() as db:
        # Find completed debate sessions that have a Bluesky URI in state
        sessions = (await db.execute(
            select(DebateSession).where(DebateSession.status == DebateStatus.COMPLETED)
        )).scalars().all()

        for session in sessions:
            state = session.debate_state or {}
            bsky = state.get("bluesky_result", {})
            uri = bsky.get("uri", "")
            if not uri:
                continue

            # Find associated content posts for this session
            posts = (await db.execute(
                select(ContentPost)
                .where(ContentPost.debate_session_id == session.id)
                .where(ContentPost.status == PostStatus.PUBLISHED)
            )).scalars().all()

            # If no linked posts yet, still queue a sync using campaign context
            # (campaign-level analytics, post_id derived from session)
            if not posts:
                # Queue with a synthetic post_id — skip gracefully if not found
                sync_post_metrics.apply_async(
                    args=[str(session.campaign_id), uri],
                    queue="analytics",
                )
                queued += 1
            else:
                for post in posts:
                    sync_post_metrics.apply_async(
                        args=[str(post.id), uri],
                        queue="analytics",
                    )
                    queued += 1

    logger.info("sync_all_bluesky_metrics: queued %d sync tasks", queued)
    return {"queued": queued, "run_at": datetime.now(timezone.utc).isoformat()}


# ───────────────────────────────────────────────────────────────
# Task 4: cleanup_stale_debates  (beat: every hour)
# ───────────────────────────────────────────────────────────────

@shared_task(name="app.workers.tasks.cleanup_stale_debates")
def cleanup_stale_debates() -> dict[str, Any]:
    """
    Periodic task (beat): find debates that have been IN_PROGRESS for more
    than 30 minutes (likely crashed workers) and mark them as FAILED.
    """
    logger.info("cleanup_stale_debates: scanning for stuck debates")
    return asyncio.run(_cleanup_async())


async def _cleanup_async() -> dict[str, Any]:
    """Async scan: mark stale debates as FAILED."""
    from app.database.session import AsyncSessionLocal
    from app.models.debate_session import DebateSession, DebateStatus

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    cleaned = 0

    async with AsyncSessionLocal() as db:
        stale = (await db.execute(
            select(DebateSession)
            .where(DebateSession.status == DebateStatus.IN_PROGRESS)
            .where(DebateSession.created_at < cutoff)
        )).scalars().all()

        for session in stale:
            session.status = DebateStatus.FAILED
            session.error_message = "Debate timed out — worker may have crashed."
            cleaned += 1

        if cleaned:
            await db.commit()

    logger.info("cleanup_stale_debates: cleaned %d stale debates", cleaned)
    return {"cleaned": cleaned, "run_at": datetime.now(timezone.utc).isoformat()}
