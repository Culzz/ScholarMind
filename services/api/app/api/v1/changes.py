"""Change feed and the admin review console.

The public feed shows only changes that have been verified - either approved by
a reviewer or auto-accepted with high confidence. Unverified diffs never reach
the public feed, because a false "deadline extended" or "deadline shortened"
post would be worse than no post at all.

The admin console exposes the queues a reviewer works through: flagged changes,
open conflicts, low-confidence extractions and scam signals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.core.security import current_admin

router = APIRouter(tags=["changes"])


class ReviewRequest(BaseModel):
    """A reviewer's decision on a flagged change."""

    decision: str = Field(default="approve", pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=1000)


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/changes")
async def changes_feed(
    session: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """The public 'what changed this week' feed (verified changes only)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.execute(
        text(
            """
            SELECT ce.id::text, ce.field_name, ce.old_value, ce.new_value, ce.change_type,
                   ce.severity, ce.detected_at, ce.review_status, ce.cycle_id::text,
                   s.name, d.url
            FROM change_events ce
            JOIN source_documents d ON d.id = ce.source_document_id
            LEFT JOIN source_snapshots ss ON ss.id = ce.new_snapshot_id
            LEFT JOIN scholarships s ON s.canonical_source_id = d.id
            WHERE ce.detected_at >= :since
              AND ce.review_status IN ('approved', 'auto_accepted')
            ORDER BY ce.detected_at DESC
            LIMIT :limit
            """
        ),
        {"since": since, "limit": limit},
    ).fetchall()

    return {
        "window_days": days,
        "items": [
            {
                "id": row[0],
                "scholarship": row[9],
                "source_url": row[10],
                "field": row[1],
                "old_value": row[2],
                "new_value": row[3],
                "change_type": row[4],
                "severity": row[5],
                "detected_at": row[6].isoformat() if row[6] else None,
                "review_status": row[7],
                "cycle_id": row[8],
            }
            for row in rows
        ],
        "note": (
            "Only reviewed or high-confidence changes are shown. A change that has not been "
            "verified is not published."
        ),
    }


@admin_router.get("/changes")
async def admin_changes(
    session: Session = Depends(get_db),
    status: str = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """The review queue of flagged changes."""
    rows = session.execute(
        text(
            """
            SELECT ce.id::text, ce.field_name, ce.old_value, ce.new_value, ce.change_type,
                   ce.severity, ce.detected_at, ce.review_status, ce.review_note,
                   d.url, s.name
            FROM change_events ce
            JOIN source_documents d ON d.id = ce.source_document_id
            LEFT JOIN scholarships s ON s.canonical_source_id = d.id
            WHERE ce.review_status = :status
            ORDER BY ce.severity DESC, ce.detected_at ASC
            LIMIT :limit
            """
        ),
        {"status": status, "limit": limit},
    ).fetchall()

    return {
        "items": [
            {
                "id": row[0],
                "field": row[1],
                "old_value": row[2],
                "new_value": row[3],
                "change_type": row[4],
                "severity": row[5],
                "detected_at": row[6].isoformat() if row[6] else None,
                "review_status": row[7],
                "review_note": row[8],
                "source_url": row[9],
                "scholarship": row[10],
            }
            for row in rows
        ]
    }


@admin_router.post("/changes/{change_id}/review")
async def review_change(
    change_id: str,
    payload: ReviewRequest,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Approve or reject a flagged change."""
    decision = (payload.decision or "").lower()
    if decision not in ("approve", "reject"):
        raise ForbiddenError("decision must be 'approve' or 'reject'.")

    row = session.execute(
        text("SELECT id::text, field_name FROM change_events WHERE id::text = :id"),
        {"id": change_id},
    ).fetchone()
    if not row:
        raise NotFoundError("Change event not found.")

    session.execute(
        text(
            """
            UPDATE change_events
            SET review_status = :status,
                reviewed_by = :reviewer,
                reviewed_at = now(),
                review_note = :note
            WHERE id::text = :id
            """
        ),
        {
            "id": change_id,
            "status": "approved" if decision == "approve" else "rejected",
            "reviewer": user.get("sub"),
            "note": payload.note,
        },
    )
    session.commit()
    return {"id": change_id, "review_status": "approved" if decision == "approve" else "rejected"}


@admin_router.get("/conflicts")
async def admin_conflicts(
    session: Session = Depends(get_db),
    status: str = Query(default="open"),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Open conflicts between official sources."""
    rows = session.execute(
        text(
            """
            SELECT id::text, entity_type, entity_id::text, field_name, value_a, value_b,
                   source_document_id_a::text, source_document_id_b::text, created_at
            FROM conflicts WHERE status = :status ORDER BY created_at DESC
            """
        ),
        {"status": status},
    ).fetchall()
    return {
        "items": [
            {
                "id": row[0],
                "entity_type": row[1],
                "entity_id": row[2],
                "field": row[3],
                "value_a": row[4],
                "value_b": row[5],
                "source_a": row[6],
                "source_b": row[7],
                "created_at": row[8].isoformat() if row[8] else None,
            }
            for row in rows
        ]
    }


@admin_router.get("/signals")
async def admin_scam_signals(
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Scam signals raised against sources."""
    rows = session.execute(
        text(
            """
            SELECT ss.id::text, ss.source_document_id::text, ss.signal_type, ss.severity,
                   ss.detail, ss.detected_at, ss.status, d.url
            FROM scam_signals ss
            JOIN source_documents d ON d.id = ss.source_document_id
            WHERE ss.status = 'open'
            ORDER BY ss.severity DESC, ss.detected_at DESC
            """
        )
    ).fetchall()
    return {
        "items": [
            {
                "id": row[0],
                "source_document_id": row[1],
                "signal_type": row[2],
                "severity": row[3],
                "detail": row[4],
                "detected_at": row[5].isoformat() if row[5] else None,
                "status": row[6],
                "source_url": row[7],
            }
            for row in rows
        ]
    }


@admin_router.get("/sources")
async def admin_sources(
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Corpus health: source status and freshness."""
    rows = session.execute(
        text(
            """
            SELECT d.id::text, d.url, d.trust_tier, d.source_type, d.fetch_status,
                   d.last_checked_at, d.last_success_at, d.consecutive_failures,
                   d.refresh_cadence_hours, d.is_enabled,
                   (SELECT count(*) FROM source_snapshots ss WHERE ss.source_document_id = d.id)
            FROM source_documents d
            ORDER BY d.url
            """
        )
    ).fetchall()
    return {
        "items": [
            {
                "id": row[0],
                "url": row[1],
                "trust_tier": row[2],
                "source_type": row[3],
                "fetch_status": row[4],
                "last_checked_at": row[5].isoformat() if row[5] else None,
                "last_success_at": row[6].isoformat() if row[6] else None,
                "consecutive_failures": row[7],
                "refresh_cadence_hours": row[8],
                "is_enabled": row[9],
                "snapshot_count": row[10],
            }
            for row in rows
        ]
    }


@admin_router.get("/jobs")
async def admin_jobs(
    session: Session = Depends(get_db),
    status: str = Query(default="failed"),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Ingestion job status, for failure visibility."""
    rows = session.execute(
        text(
            """
            SELECT j.id::text, j.source_document_id::text, j.task_id, j.status, j.attempts,
                   j.last_error, j.started_at, j.finished_at, d.url
            FROM ingestion_jobs j
            JOIN source_documents d ON d.id = j.source_document_id
            WHERE j.status = :status
            ORDER BY j.created_at DESC
            LIMIT 200
            """
        ),
        {"status": status},
    ).fetchall()
    return {
        "items": [
            {
                "id": row[0],
                "source_document_id": row[1],
                "task_id": row[2],
                "status": row[3],
                "attempts": row[4],
                "last_error": row[5],
                "started_at": row[6].isoformat() if row[6] else None,
                "finished_at": row[7].isoformat() if row[7] else None,
                "source_url": row[8],
            }
            for row in rows
        ]
    }
