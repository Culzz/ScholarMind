"""Snapshotting: turning a fetch into an immutable, auditable capture.

A snapshot is the unit of provenance for everything downstream. It records the
raw bytes, the normalised text, the response metadata, the content hash and the
time of capture. Snapshots are never mutated; a change is expressed as a new
snapshot plus a ``change_event`` referencing both.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from scholarmind.ingestion.fetcher import FetchResult, hash_content


@dataclass(frozen=True)
class Snapshot:
    """An immutable capture of a source document."""

    source_document_id: str
    content_hash: str
    extracted_text: str
    fetched_at: datetime
    http_status: int | None = None
    headers: dict[str, str] | None = None
    raw_content: bytes | None = None
    fetched_by: str = "scheduler"
    extraction_version: str = "1"

    @property
    def text_hash(self) -> str:
        """Hash of the normalised text (used to ignore cosmetic-only changes)."""
        return hashlib.sha256(self.extracted_text.encode("utf-8")).hexdigest()

    def to_record(self) -> dict[str, Any]:
        """Serialisable representation for persistence."""
        return {
            "source_document_id": self.source_document_id,
            "content_hash": self.content_hash,
            "extracted_text": self.extracted_text,
            "fetched_at": self.fetched_at,
            "http_status": self.http_status,
            "headers": self.headers or {},
            "fetched_by": self.fetched_by,
            "extraction_version": self.extraction_version,
        }


def snapshot_from_fetch(
    result: FetchResult,
    *,
    source_document_id: str,
    text: str,
    fetched_by: str = "scheduler",
) -> Snapshot:
    """Build a snapshot from a successful fetch and its normalised text."""
    return Snapshot(
        source_document_id=source_document_id,
        content_hash=result.content_hash or hash_content(result.content),
        extracted_text=text,
        fetched_at=result.fetched_at or datetime.now(timezone.utc),
        http_status=result.status_code,
        headers=dict(result.headers),
        raw_content=result.content,
        fetched_by=fetched_by,
    )


def is_new_content(previous_hash: str | None, snapshot: Snapshot) -> bool:
    """Whether a snapshot represents genuinely new content.

    An unchanged content hash means there is nothing to diff, and the change
    detector must not raise an event for it.
    """
    return previous_hash is None or previous_hash != snapshot.content_hash
