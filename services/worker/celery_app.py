"""Celery application for background processing.

Tasks are idempotent and bounded: every task carries a deterministic key so a
retry re-does the same work rather than duplicating it. A single beat instance
should run in production — duplicate schedules would double-fetch sources.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("scholarmind", broker=BROKER_URL, backend=RESULT_BACKEND)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600 * 24,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "refresh-sources": {
            "task": "scholarmind.refresh_sources",
            "schedule": crontab(minute=0),  # hourly
        },
        "staleness-sweep": {
            "task": "scholarmind.staleness_sweep",
            "schedule": crontab(hour=3, minute=0),  # daily 03:00 UTC
        },
        "dispatch-alerts": {
            "task": "scholarmind.dispatch_alerts",
            "schedule": 900.0,  # every 15 minutes
        },
        "retry-failed-ingestion": {
            "task": "scholarmind.retry_failed_ingestion",
            "schedule": crontab(hour=4, minute=30),  # daily
        },
    },
)

celery_app.autodiscover_tasks(["services.worker.tasks"])
