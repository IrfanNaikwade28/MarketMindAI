"""
app/workers/celery_app.py
--------------------------
Celery application factory.

Configuration:
  - Broker:          Redis (same instance as the app)
  - Result backend:  Redis (separate DB index)
  - Serializer:      JSON (safe, readable)
  - Task discovery:  app.workers.tasks

Beat schedule (periodic tasks):
  - analytics-sync:  every 30 minutes — pull Bluesky engagement for all
                     published posts and upsert into Analytics table.

Usage:
  Start worker:
    cd backend && source venv/bin/activate
    celery -A app.workers.celery_app worker --loglevel=info

  Start beat scheduler (periodic tasks):
    celery -A app.workers.celery_app beat --loglevel=info

  Combined (development only):
    celery -A app.workers.celery_app worker --beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from app.config.settings import get_settings

settings = get_settings()

# ── Create the Celery app ───────────────────────────────────────
celery_app = Celery(
    "ai_council",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

# ── Celery configuration ────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behaviour
    task_track_started=True,         # emit STARTED state when task begins
    task_acks_late=True,             # acknowledge after task completes (safer)
    worker_prefetch_multiplier=1,    # process one task at a time per worker
    task_reject_on_worker_lost=True, # re-queue if worker dies mid-task

    # Result expiry
    result_expires=86400,            # keep results for 24 hours

    # Retry defaults
    task_max_retries=3,
    task_default_retry_delay=60,     # 1 minute between retries
)

# ── Beat schedule (periodic tasks) ─────────────────────────────
celery_app.conf.beat_schedule = {
    # Sync Bluesky engagement metrics every 30 minutes
    "analytics-bluesky-sync": {
        "task":     "app.workers.tasks.sync_all_bluesky_metrics",
        "schedule": crontab(minute="*/30"),
        "options":  {"queue": "analytics"},
    },
    # Clean up stale in-progress debates every hour
    # (catches debates that crashed without updating their status)
    "cleanup-stale-debates": {
        "task":     "app.workers.tasks.cleanup_stale_debates",
        "schedule": crontab(minute=0),   # top of every hour
        "options":  {"queue": "maintenance"},
    },
}

# ── Queue routing ───────────────────────────────────────────────
celery_app.conf.task_routes = {
    "app.workers.tasks.run_debate_task":         {"queue": "debates"},
    "app.workers.tasks.sync_all_bluesky_metrics": {"queue": "analytics"},
    "app.workers.tasks.sync_post_metrics":       {"queue": "analytics"},
    "app.workers.tasks.cleanup_stale_debates":   {"queue": "maintenance"},
}
