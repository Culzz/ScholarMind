"""Conflict resolution with a trust hierarchy.

When two official sources disagree, the platform does not pick a winner
silently. It ranks the sources by trust tier, *proposes* the higher-tier value,
and keeps the conflict open for human review whenever the disagreement is
material (deadline, funding, eligibility).

The proposal is a hint for the reviewer and for the UI's "likely value" display.
It never becomes a confirmed fact on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

# Higher number = more authoritative.
TRUST_HIERARCHY: dict[str, int] = {
    "official_primary": 5,
    "official_secondary": 4,
    "partner": 3,
    "aggregator": 1,
}

# Fields where a disagreement is material enough to require human review.
MATERIAL_FIELDS = {
    "deadline_at",
    "deadline_raw_text",
    "opens_at",
    "funding_components",
    "eligibility_rules",
    "required_documents",
}


@dataclass
class SourceValue:
    """A value asserted by one source."""

    source_document_id: str
    value: Any
    trust_tier: str
    evidence_id: str | None = None
    checked_at: str | None = None
    source_url: str | None = None

    @property
    def rank(self) -> int:
        return TRUST_HIERARCHY.get(self.trust_tier, 0)


@dataclass
class ConflictResolution:
    """The proposed resolution of a conflict."""

    field_name: str
    proposed_value: Any
    proposed_source_document_id: str
    competing_value: Any
    competing_source_document_id: str
    requires_review: bool
    reason: str
    trust_ranks: list[tuple[str, str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "proposed_value": self.proposed_value,
            "proposed_source_document_id": self.proposed_source_document_id,
            "competing_value": self.competing_value,
            "competing_source_document_id": self.competing_source_document_id,
            "requires_review": self.requires_review,
            "reason": self.reason,
            "trust_ranks": [
                {"source_document_id": source_id, "trust_tier": tier, "rank": rank}
                for source_id, tier, rank in self.trust_ranks
            ],
        }


def resolve_conflict(
    *,
    field_name: str,
    sources: Sequence[SourceValue],
) -> ConflictResolution | None:
    """Propose a resolution for a conflict between two sources.

    Returns ``None`` when the sources agree (there is no conflict to resolve).
    """
    if len(sources) < 2:
        return None

    values = [source for source in sources if source.value is not None]
    distinct = {repr(source.value) for source in values}
    if len(distinct) < 2:
        return None

    ranked = sorted(values, key=lambda source: source.rank, reverse=True)
    winner = ranked[0]
    runner_up = ranked[1]

    same_tier = winner.rank == runner_up.rank
    material = field_name in MATERIAL_FIELDS

    if same_tier:
        reason = (
            f"Both sources have the same trust tier ({winner.trust_tier}), so no value is "
            "preferred automatically. A reviewer must decide."
        )
        requires_review = True
    elif material:
        reason = (
            f"The higher-trust source ({winner.trust_tier}) states a different value, but "
            f"'{field_name}' is a material field, so a reviewer must confirm before it is "
            "treated as confirmed."
        )
        requires_review = True
    else:
        reason = (
            f"The higher-trust source ({winner.trust_tier}) is preferred for this "
            "non-material field, but the conflict remains visible."
        )
        requires_review = False

    return ConflictResolution(
        field_name=field_name,
        proposed_value=winner.value,
        proposed_source_document_id=winner.source_document_id,
        competing_value=runner_up.value,
        competing_source_document_id=runner_up.source_document_id,
        requires_review=requires_review,
        reason=reason,
        trust_ranks=[(source.source_document_id, source.trust_tier, source.rank) for source in ranked],
    )


def conflict_display_state(
    *,
    field_name: str,
    sources: Sequence[SourceValue],
    resolution: ConflictResolution | None,
) -> str:
    """The claim state to show for a conflicting field.

    Conflicting fields are shown as ``needs_verification`` regardless of the
    proposed resolution: the user should see that the sources disagree.
    """
    if resolution is None:
        return "confirmed"
    if resolution.requires_review:
        return "needs_verification"
    return "needs_verification"


def summarise_sources(sources: Sequence[SourceValue]) -> list[dict[str, Any]]:
    """Source summary for the conflict UI."""
    return [
        {
            "source_document_id": source.source_document_id,
            "trust_tier": source.trust_tier,
            "rank": source.rank,
            "value": source.value,
            "evidence_id": source.evidence_id,
            "checked_at": source.checked_at,
            "source_url": source.source_url,
        }
        for source in sorted(sources, key=lambda s: s.rank, reverse=True)
    ]


def conflict_age_days(conflict: dict[str, Any], *, today: date | None = None) -> int | None:
    """How long a conflict has been open, for prioritisation in the review queue."""
    created = conflict.get("created_at")
    if not created:
        return None
    reference = today or date.today()
    if isinstance(created, str):
        try:
            created_date = date.fromisoformat(created[:10])
        except ValueError:
            return None
    elif isinstance(created, date):
        created_date = created
    else:
        return None
    return (reference - created_date).days
