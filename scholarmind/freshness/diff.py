"""Freshness: snapshot diffing, change classification and conflict detection.

The change detector compares the *structured facts* extracted from two snapshots
rather than raw page text. Field-level comparison produces far fewer false alarms
than a text diff, because a reformatted paragraph or a rotating banner is not a
policy change.

Severity policy
---------------
``critical``      deadline, opening date, funding, eligibility, required documents.
``important``     process and contact changes that affect how a student applies.
``informational`` cosmetic edits, navigation, typos.

A change never silently rewrites a confirmed fact: candidates are emitted with
``review_status='pending'`` (or auto-accepted only when the extractor confidence
exceeds the configured threshold and the change is informational).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

CRITICAL_FIELDS = {
    "deadline_at",
    "deadline_raw_text",
    "opens_at",
    "funding_components",
    "eligibility_rules",
    "required_documents",
}

IMPORTANT_FIELDS = {"process", "contact", "portal_url", "application_method"}

FIELD_TO_CHANGE_TYPE = {
    "deadline_at": "deadline",
    "deadline_raw_text": "deadline",
    "opens_at": "opening_date",
    "funding_components": "funding",
    "eligibility_rules": "eligibility",
    "required_documents": "document",
    "process": "process",
    "contact": "contact",
    "portal_url": "process",
    "application_method": "process",
}


class ChangeType(str, Enum):
    DEADLINE = "deadline"
    OPENING_DATE = "opening_date"
    FUNDING = "funding"
    ELIGIBILITY = "eligibility"
    DOCUMENT = "document"
    PROCESS = "process"
    CONTACT = "contact"
    COSMETIC = "cosmetic"


class Severity(str, Enum):
    INFORMATIONAL = "informational"
    IMPORTANT = "important"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ChangeEvent:
    """A detected difference between two snapshots of the same source."""

    field_name: str
    old_value: Any
    new_value: Any
    change_type: ChangeType
    severity: Severity
    detected_at: str
    confidence: float = 1.0
    review_status: str = "pending"
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "detected_at": self.detected_at,
            "confidence": self.confidence,
            "review_status": self.review_status,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class Conflict:
    """Two official sources disagreeing about the same field."""

    entity_type: str
    entity_id: str
    field_name: str
    value_a: Any
    value_b: Any
    source_document_id_a: str
    source_document_id_b: str
    evidence_id_a: str | None = None
    evidence_id_b: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "field_name": self.field_name,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "source_document_id_a": self.source_document_id_a,
            "source_document_id_b": self.source_document_id_b,
            "evidence_id_a": self.evidence_id_a,
            "evidence_id_b": self.evidence_id_b,
            "status": "open",
        }


def classify_field(field_name: str) -> tuple[ChangeType, Severity]:
    """Map a structured field name to a change type and severity."""
    change_type = FIELD_TO_CHANGE_TYPE.get(field_name)
    if change_type is None:
        return ChangeType.COSMETIC, Severity.INFORMATIONAL
    if field_name in CRITICAL_FIELDS:
        return change_type, Severity.CRITICAL
    if field_name in IMPORTANT_FIELDS:
        return change_type, Severity.IMPORTANT
    return change_type, Severity.INFORMATIONAL


def diff_facts(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    detected_at: str,
    min_confidence: float = 0.0,
) -> list[ChangeEvent]:
    """Compare two fact mappings and emit change events for the differences."""
    events: list[ChangeEvent] = []
    for field_name in sorted(set(old) | set(new)):
        old_value = old.get(field_name)
        new_value = new.get(field_name)
        if old_value == new_value:
            continue
        change_type, severity = classify_field(field_name)
        if severity is Severity.INFORMATIONAL and field_name not in old and field_name not in new:
            continue
        events.append(
            ChangeEvent(
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                change_type=change_type,
                severity=severity,
                detected_at=detected_at,
            )
        )
    return [event for event in events if event.confidence >= min_confidence]


def detect_conflicts(
    *,
    entity_type: str,
    entity_id: str,
    field_name: str,
    sources: Sequence[tuple[str, Any, str | None]],
) -> list[Conflict]:
    """Find disagreement between official sources for one field.

    Parameters
    ----------
    sources:
        Sequence of ``(source_document_id, value, evidence_id)`` tuples.

    Returns
    -------
    list[Conflict]
        One conflict per differing value pair. More than two disagreeing sources
        produce multiple pairwise conflicts, all of which are surfaced.
    """
    conflicts: list[Conflict] = []
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            id_a, value_a, ev_a = sources[i]
            id_b, value_b, ev_b = sources[j]
            if id_a == id_b or value_a == value_b:
                continue
            if value_a is None or value_b is None:
                # An unknown value is not a contradiction; it is an absence of evidence.
                continue
            conflicts.append(
                Conflict(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_name=field_name,
                    value_a=value_a,
                    value_b=value_b,
                    source_document_id_a=id_a,
                    source_document_id_b=id_b,
                    evidence_id_a=ev_a,
                    evidence_id_b=ev_b,
                )
            )
    return conflicts


def stale_threshold(cadence_hours: int, multiplier: int = 2) -> float:
    """Hours after which a source is considered stale relative to its cadence."""
    return max(cadence_hours, 1) * multiplier


def summarize_changes(events: Iterable[ChangeEvent]) -> dict[str, int]:
    """Counts by change type, used by dashboards and the change-history feed."""
    summary: dict[str, int] = {change_type.value: 0 for change_type in ChangeType}
    for event in events:
        summary[event.change_type.value] += 1
    return summary
