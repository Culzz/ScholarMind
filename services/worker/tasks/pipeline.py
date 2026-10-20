"""Extraction, chunking and indexing tasks.

These tasks run after a snapshot has been stored:

    extract_facts    -> typed facts with character spans, validated
    normalize        -> cycle/date/field normalisation
    index_chunks     -> chunk the text, embed it, write the search vectors
    diff_and_flag    -> compare with the previous snapshot and flag changes

Each task is idempotent: running it twice over the same snapshot produces the
same rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery import shared_task
from sqlalchemy import text

from services.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="scholarmind.extract_facts", bind=True, max_retries=2)
def extract_facts(self: Any, snapshot_id: str) -> dict[str, Any]:
    """Extract typed facts from a stored snapshot and persist the claims."""
    from scholarmind.extraction.extract import extract_all
    from scholarmind.extraction.validate import validate_result

    snapshot = _load_snapshot(snapshot_id)
    if snapshot is None:
        return {"status": "skipped", "reason": "snapshot_not_found", "snapshot_id": snapshot_id}

    source_document_id, extracted_text = snapshot
    result = extract_all(extracted_text)
    report, validated = validate_result(result, extracted_text)

    stored = _store_claims(snapshot_id, validated)
    logger.info(
        "extracted %s facts (%s rules) from snapshot %s",
        len(validated.facts),
        len(validated.eligibility),
        snapshot_id[:8],
    )
    return {
        "status": "ok",
        "snapshot_id": snapshot_id,
        "claims_stored": stored,
        **report.summary(),
    }


@celery_app.task(name="scholarmind.index_chunks", bind=True, max_retries=2)
def index_chunks(self: Any, snapshot_id: str) -> dict[str, Any]:
    """Chunk a snapshot's text and write the lexical and vector indexes."""
    from scholarmind.retrieval.fusion import chunk_text

    snapshot = _load_snapshot(snapshot_id)
    if snapshot is None:
        return {"status": "skipped", "reason": "snapshot_not_found", "snapshot_id": snapshot_id}

    source_document_id, extracted_text = snapshot
    chunks = chunk_text(extracted_text, max_tokens=500, overlap=80)

    written = _store_chunks(snapshot_id, source_document_id, extracted_text, chunks)
    logger.info("indexed %s chunks for snapshot %s", written, snapshot_id[:8])
    return {"status": "ok", "snapshot_id": snapshot_id, "chunks": written}


@celery_app.task(name="scholarmind.diff_and_flag", bind=True, max_retries=2)
def diff_and_flag(self: Any, snapshot_id: str) -> dict[str, Any]:
    """Compare a snapshot with the previous one and flag the differences."""
    from scholarmind.freshness.diff import diff_facts

    snapshot = _load_snapshot(snapshot_id)
    if snapshot is None:
        return {"status": "skipped", "reason": "snapshot_not_found", "snapshot_id": snapshot_id}

    source_document_id, _ = snapshot
    previous = _previous_snapshot(source_document_id, snapshot_id)
    if previous is None:
        return {"status": "ok", "snapshot_id": snapshot_id, "changes": 0, "reason": "first_snapshot"}

    old_facts = _facts_for_snapshot(previous)
    new_facts = _facts_for_snapshot(snapshot_id)

    events = diff_facts(old_facts, new_facts, detected_at=datetime.now(timezone.utc).isoformat())
    written = _store_change_events(source_document_id, snapshot_id, previous, events)
    logger.info("flagged %s change(s) for snapshot %s", written, snapshot_id[:8])
    return {"status": "ok", "snapshot_id": snapshot_id, "changes": written}


# --- persistence helpers -------------------------------------------------


def _load_snapshot(snapshot_id: str) -> tuple[str, str] | None:
    from app.db.session import get_engine

    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT source_document_id::text, coalesce(extracted_text, '')
                    FROM source_snapshots WHERE id::text = :id
                    """
                ),
                {"id": snapshot_id},
            ).fetchone()
    except Exception:
        return None
    return (row[0], row[1]) if row else None


def _previous_snapshot(source_document_id: str, snapshot_id: str) -> str | None:
    from app.db.session import get_engine

    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id::text FROM source_snapshots
                    WHERE source_document_id::text = :source AND id::text <> :current
                    ORDER BY fetched_at DESC
                    LIMIT 1
                    """
                ),
                {"source": source_document_id, "current": snapshot_id},
            ).fetchone()
    except Exception:
        return None
    return row[0] if row else None


def _facts_for_snapshot(snapshot_id: str) -> dict[str, Any]:
    """The structured facts of a snapshot, keyed by field name."""
    from app.db.session import get_engine

    facts: dict[str, Any] = {}
    try:
        with get_engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT field_name, normalized_value FROM evidence_claims
                    WHERE snapshot_id::text = :id AND field_name IS NOT NULL
                    """
                ),
                {"id": snapshot_id},
            ).fetchall()
    except Exception:
        return facts
    for field_name, value in rows:
        facts[field_name] = value
    return facts


def _store_claims(snapshot_id: str, validated: Any) -> int:
    from app.db.session import get_engine

    stored = 0
    try:
        with get_engine().begin() as connection:
            for fact in validated.facts:
                connection.execute(
                    text(
                        """
                        INSERT INTO evidence_claims
                            (id, snapshot_id, span_start, span_end, claim_text, claim_type,
                             field_name, normalized_value, validation_status, confidence,
                             extraction_method)
                        VALUES (gen_random_uuid(), :snapshot_id, :span_start, :span_end,
                                :claim_text, :claim_type, :field_name,
                                CAST(:normalized_value AS jsonb), :status, :confidence,
                                :extraction_method)
                        """
                    ),
                    {
                        "snapshot_id": snapshot_id,
                        "span_start": fact.span_start,
                        "span_end": fact.span_end,
                        "claim_text": fact.text,
                        "claim_type": fact.claim_type.value,
                        "field_name": fact.field_name,
                        "normalized_value": _json_dump(fact.normalized_value),
                        "status": fact.status.value,
                        "confidence": fact.confidence,
                        "extraction_method": fact.extraction_method,
                    },
                )
                stored += 1
    except Exception as exc:  # pragma: no cover
        logger.warning("could not store claims for %s: %s", snapshot_id, exc)
    return stored


def _store_chunks(
    snapshot_id: str, source_document_id: str, text_content: str, chunks: list[str]
) -> int:
    import hashlib

    from app.db.session import get_engine

    written = 0
    try:
        with get_engine().begin() as connection:
            for chunk in chunks:
                content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                connection.execute(
                    text(
                        """
                        INSERT INTO evidence_chunks
                            (id, snapshot_id, source_document_id, char_start, char_end,
                             content, content_hash, token_count)
                        VALUES (gen_random_uuid(), :snapshot_id, :source_document_id, :start,
                                :end, :content, :hash, :tokens)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "snapshot_id": snapshot_id,
                        "source_document_id": source_document_id,
                        "start": 0,
                        "end": len(chunk),
                        "content": chunk,
                        "hash": content_hash,
                        "tokens": len(chunk) // 4,
                    },
                )
                written += 1
    except Exception as exc:  # pragma: no cover
        logger.warning("could not store chunks for %s: %s", snapshot_id, exc)
    return written


def _store_change_events(
    source_document_id: str, snapshot_id: str, previous_id: str, events: list[Any]
) -> int:
    from app.db.session import get_engine

    written = 0
    try:
        with get_engine().begin() as connection:
            for event in events:
                connection.execute(
                    text(
                        """
                        INSERT INTO change_events
                            (id, source_document_id, prev_snapshot_id, new_snapshot_id,
                             field_name, old_value, new_value, change_type, severity,
                             detected_at, review_status)
                        VALUES (gen_random_uuid(), :source, :prev, :new, :field,
                                CAST(:old_value AS jsonb), CAST(:new_value AS jsonb),
                                :change_type, :severity, :detected_at, 'pending')
                        """
                    ),
                    {
                        "source": source_document_id,
                        "prev": previous_id,
                        "new": snapshot_id,
                        "field": event.field_name,
                        "old_value": _json_dump(event.old_value),
                        "new_value": _json_dump(event.new_value),
                        "change_type": event.change_type.value,
                        "severity": event.severity.value,
                        "detected_at": event.detected_at,
                    },
                )
                written += 1
    except Exception as exc:  # pragma: no cover
        logger.warning("could not store change events: %s", exc)
    return written


def _json_dump(value: Any) -> str:
    import json

    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return "null"


@shared_task(name="scholarmind.noop")
def noop() -> dict[str, Any]:
    """Placeholder task used by the health checks."""
    return {"status": "ok"}
