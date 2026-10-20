"""Ingestion tasks.

The pipeline is deliberately explicit so each stage can fail independently and be
retried without redoing successful work:

    refresh_sources  -> picks the sources whose cadence has elapsed
    fetch_snapshot   -> downloads and stores an immutable snapshot
    extract_facts    -> typed facts with character spans  (phase 3)
    normalize        -> cycle/date/field normalization    (phase 3)
    diff_and_flag    -> compares with the previous snapshot and flags changes

Tasks are idempotent: re-running them with the same input produces the same
state, and a duplicated queue message is a no-op.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from celery import shared_task

from services.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = ROOT / "data" / "manifests" / "nigeria_v1.yaml"


def _manifest_path() -> Path:
    import os

    configured = os.getenv("SCHOLARMIND_MANIFEST")
    return Path(configured) if configured else DEFAULT_MANIFEST


@celery_app.task(name="scholarmind.refresh_sources", bind=True, max_retries=3)
def refresh_sources(self: Any, manifest_path: str | None = None) -> dict[str, Any]:
    """Select due sources and queue a fetch for each."""
    from scholarmind.ingestion.manifest import load_manifest

    path = Path(manifest_path) if manifest_path else _manifest_path()
    manifest = load_manifest(path)

    if not _ingestion_enabled():
        logger.info("ingestion disabled; skipping refresh for %s sources", len(manifest))
        return {"status": "skipped", "reason": "ingestion_disabled", "sources": len(manifest)}

    last_checked = _load_last_checked()
    from scholarmind.ingestion.manifest import due_sources

    due = due_sources(manifest, last_checked)
    for source in due:
        fetch_snapshot.apply_async(args=[source.url, source.trust_tier], queue="ingestion")

    logger.info("queued %s/%s sources for refresh", len(due), len(manifest))
    return {"status": "queued", "queued": len(due), "total": len(manifest)}


@celery_app.task(name="scholarmind.fetch_snapshot", bind=True, max_retries=3)
def fetch_snapshot(self: Any, url: str, trust_tier: str = "official_primary") -> dict[str, Any]:
    """Fetch one allowlisted source and store a snapshot."""
    from scholarmind.ingestion.fetcher import SafeFetcher
    from scholarmind.ingestion.manifest import load_manifest
    from scholarmind.ingestion.safety import build_policy
    from scholarmind.ingestion.snapshot import snapshot_from_fetch

    manifest = load_manifest(_manifest_path())
    if url not in manifest.urls:
        logger.warning("refusing to fetch non-manifest url: %s", url)
        return {"status": "refused", "reason": "not_in_manifest", "url": url}

    from app.core.http import build_http_client

    policy = build_policy([url])
    fetcher = SafeFetcher(
        policy,
        user_agent=_user_agent(),
        client=build_http_client(user_agent=_user_agent()),
    )
    text, result = fetcher.fetch_text(url)

    if not result.ok:
        logger.warning("fetch failed for %s: %s", url, result.error)
        _record_fetch_failure(url, result.error)
        return {"status": "failed", "url": url, "error": result.error}

    source_document_id = _upsert_source_document(url, trust_tier)
    snapshot = snapshot_from_fetch(result, source_document_id=source_document_id, text=text)

    if not _ingestion_enabled():
        return {"status": "dry_run", "url": url, "content_hash": snapshot.content_hash}

    stored = _store_snapshot(snapshot)
    _record_fetch_success(url, snapshot.fetched_at)

    from scholarmind.ingestion.scam_signals import collect_signals, summarise_signals

    signals = collect_signals(url=url, text=text, trust_tier=trust_tier)
    _store_scam_signals(source_document_id, signals)

    logger.info("snapshot stored for %s (%s)", url, snapshot.content_hash[:12])
    return {
        "status": "ok",
        "url": url,
        "content_hash": snapshot.content_hash,
        "snapshot_id": stored,
        "scam_signals": summarise_signals(signals),
    }


@celery_app.task(name="scholarmind.staleness_sweep")
def staleness_sweep() -> dict[str, Any]:
    """Mark sources that have not been checked within their cadence as stale."""
    from sqlalchemy import text

    from app.db.session import get_engine

    engine = get_engine()
    statement = text(
        """
        UPDATE source_documents
        SET fetch_status = 'stale',
            updated_at = now()
        WHERE is_enabled = true
          AND last_success_at IS NOT NULL
          AND last_success_at < now() - (refresh_cadence_hours * interval '1 hour') * 2
        RETURNING id
        """
    )
    with engine.begin() as connection:
        result = connection.execute(statement)
        count = len(list(result))
    logger.info("staleness sweep marked %s sources stale", count)
    return {"status": "ok", "stale_sources": count}


@celery_app.task(name="scholarmind.dispatch_alerts")
def dispatch_alerts() -> dict[str, Any]:
    """Placeholder for the alert dispatcher (phase 7)."""
    logger.info("alert dispatch tick")
    return {"status": "ok", "sent": 0}


@celery_app.task(name="scholarmind.retry_failed_ingestion")
def retry_failed_ingestion() -> dict[str, Any]:
    """Re-queue ingestion jobs that failed below the attempt ceiling."""
    from sqlalchemy import text

    from app.db.session import get_engine

    engine = get_engine()
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT source_document_id, attempts
                FROM ingestion_jobs
                WHERE status = 'failed' AND attempts < 5
                ORDER BY created_at
                LIMIT 100
                """
            )
        ).fetchall()
    for row in rows:
        url = _source_url(row.source_document_id)
        if url:
            fetch_snapshot.apply_async(args=[url], queue="ingestion")
    return {"status": "ok", "requeued": len(rows)}


# --- persistence helpers -------------------------------------------------


def _ingestion_enabled() -> bool:
    import os

    return os.getenv("INGESTION_ENABLED", "false").lower() in ("1", "true", "yes")


def _user_agent() -> str:
    import os

    return os.getenv("INGESTION_USER_AGENT", "ScholarMindBot/1.0")


def _load_last_checked() -> dict[str, Any]:
    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        with get_engine().connect() as connection:
            rows = connection.execute(
                text("SELECT url, last_success_at FROM source_documents")
            ).fetchall()
    except Exception:  # database unavailable during local development
        return {}
    return {row.url: row.last_success_at for row in rows if row.last_success_at}


def _upsert_source_document(url: str, trust_tier: str) -> str:
    from sqlalchemy import text

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                INSERT INTO source_documents (id, url, source_type, trust_tier, fetch_status)
                VALUES (gen_random_uuid(), :url, 'other', :trust_tier, 'ok')
                ON CONFLICT (url) DO UPDATE SET trust_tier = EXCLUDED.trust_tier, updated_at = now()
                RETURNING id
                """
            ),
            {"url": url, "trust_tier": trust_tier},
        ).first()
    return str(row[0])


def _store_snapshot(snapshot: Any) -> str:
    from sqlalchemy import text

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                INSERT INTO source_snapshots
                    (id, source_document_id, content_hash, extracted_text, http_status,
                     headers, fetched_at, fetched_by, extraction_version)
                VALUES (gen_random_uuid(), :source_document_id, :content_hash, :extracted_text,
                        :http_status, CAST(:headers AS jsonb), :fetched_at, :fetched_by, :extraction_version)
                ON CONFLICT (source_document_id, content_hash) DO UPDATE
                    SET fetched_at = EXCLUDED.fetched_at
                RETURNING id
                """
            ),
            {
                "source_document_id": snapshot.source_document_id,
                "content_hash": snapshot.content_hash,
                "extracted_text": snapshot.extracted_text,
                "http_status": snapshot.http_status,
                "headers": "{}",
                "fetched_at": snapshot.fetched_at,
                "fetched_by": snapshot.fetched_by,
                "extraction_version": snapshot.extraction_version,
            },
        ).first()
    return str(row[0])


def _record_fetch_success(url: str, when: datetime) -> None:
    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE source_documents
                    SET last_checked_at = :when, last_success_at = :when, fetch_status = 'ok',
                        fetch_error = NULL, consecutive_failures = 0, updated_at = now()
                    WHERE url = :url
                    """
                ),
                {"url": url, "when": when},
            )
    except Exception as exc:  # pragma: no cover - best effort bookkeeping
        logger.warning("could not record fetch success for %s: %s", url, exc)


def _record_fetch_failure(url: str, error: str | None) -> None:
    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE source_documents
                    SET last_checked_at = now(), fetch_status = 'error', fetch_error = :error,
                        consecutive_failures = consecutive_failures + 1, updated_at = now()
                    WHERE url = :url
                    """
                ),
                {"url": url, "error": error},
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("could not record fetch failure for %s: %s", url, exc)


def _store_scam_signals(source_document_id: str, signals: list[Any]) -> None:
    if not signals:
        return
    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        with get_engine().begin() as connection:
            for signal in signals:
                connection.execute(
                    text(
                        """
                        INSERT INTO scam_signals
                            (id, source_document_id, signal_type, severity, detail, detection_method, status)
                        VALUES (gen_random_uuid(), :source_document_id, :signal_type, :severity,
                                :detail, :detection_method, 'open')
                        """
                    ),
                    {
                        "source_document_id": source_document_id,
                        "signal_type": signal.signal_type,
                        "severity": signal.severity,
                        "detail": signal.detail,
                        "detection_method": signal.detection_method,
                    },
                )
    except Exception as exc:  # pragma: no cover
        logger.warning("could not store scam signals: %s", exc)


def _source_url(source_document_id: Any) -> str | None:
    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text("SELECT url FROM source_documents WHERE id = :id"),
                {"id": str(source_document_id)},
            ).first()
    except Exception:  # pragma: no cover
        return None
    return row[0] if row else None


@shared_task(name="scholarmind.worker_heartbeat")
def worker_heartbeat() -> dict[str, Any]:
    """Publish a heartbeat so the API health check can report worker liveness."""
    import os

    try:
        import redis

        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        client.setex("scholarmind:worker:heartbeat", 300, datetime.now(timezone.utc).isoformat())
    except Exception as exc:  # pragma: no cover
        logger.warning("heartbeat failed: %s", exc)
    return {"status": "ok", "at": datetime.now(timezone.utc).isoformat()}


__all__ = [
    "celery_app",
    "dispatch_alerts",
    "fetch_snapshot",
    "refresh_sources",
    "retry_failed_ingestion",
    "staleness_sweep",
    "worker_heartbeat",
]

# Keep timedelta imported for downstream tasks that schedule future checks.
_ = timedelta
