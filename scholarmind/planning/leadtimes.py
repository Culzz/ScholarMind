"""Document lead times.

How long a document actually takes is a planning fact, and getting it wrong
makes a plan useless. The defaults below reflect the African applicant
context: transcripts issued by a registrar, referee letters that depend on a
lecturer's availability, the NYSC certificate (issued only after service
completes), credential evaluation for foreign degrees, notarisation and
apostille.

Each lead time is a **planning estimate**, configurable per document type and
per country, and always overridable by the student. The planner uses it to work
backwards from the application deadline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Default preparation lead time in days, per document type.
DEFAULT_LEAD_TIMES: dict[str, int] = {
    "passport": 21,
    "birth_certificate": 14,
    "national_id": 7,
    "ielts": 30,
    "toefl": 30,
    "english_test": 30,
    "transcript": 14,
    "certificate": 14,
    "nysc": 21,
    "statement_of_purpose": 21,
    "sop": 21,
    "cv": 7,
    "lor": 28,
    "research_proposal": 45,
    "proof_of_registration": 7,
    "proof_of_admission": 7,
    "credential_evaluation": 30,
    "apostille": 21,
    "waiver": 30,
}

# Documents that depend on a third party and therefore carry a longer default.
THIRD_PARTY_DOCUMENTS = {"lor", "transcript", "credential_evaluation", "nysc", "apostille"}

# Country-specific adjustments in days (added to the default).
COUNTRY_ADJUSTMENTS: dict[str, dict[str, int]] = {
    "NGA": {"nysc": 21, "transcript": 7, "credential_evaluation": 14},
    "GHA": {"transcript": 7},
    "KEN": {"credential_evaluation": 7},
    "ZAF": {"credential_evaluation": 7},
    "UGA": {"transcript": 10, "credential_evaluation": 21},
    "ETH": {"transcript": 14, "credential_evaluation": 21},
}

# Buffer applied to the application deadline itself.
DEFAULT_SUBMISSION_BUFFER_DAYS = 7


@dataclass(frozen=True)
class LeadTime:
    """The preparation lead time for one document."""

    doc_type: str
    days: int
    depends_on_third_party: bool
    country_adjusted: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "days": self.days,
            "depends_on_third_party": self.depends_on_third_party,
            "country_adjusted": self.country_adjusted,
            "notes": self.notes,
        }


def lead_time_for(
    doc_type: str,
    *,
    country_iso3: str | None = None,
    overrides: dict[str, int] | None = None,
) -> LeadTime:
    """The lead time for a document type, adjusted for the student's country."""
    overrides = overrides or {}
    base = overrides.get(doc_type, DEFAULT_LEAD_TIMES.get(doc_type, 14))
    adjusted = False
    notes = ""

    if country_iso3 and country_iso3 in COUNTRY_ADJUSTMENTS:
        extra = COUNTRY_ADJUSTMENTS[country_iso3].get(doc_type)
        if extra:
            base += extra
            adjusted = True
            notes = f"Includes {extra} extra days for {country_iso3}."

    if doc_type in THIRD_PARTY_DOCUMENTS:
        notes = (notes + " " if notes else "") + (
            "Depends on a third party (registrar, referee, evaluation service), so the "
            "estimate is less certain."
        )

    return LeadTime(
        doc_type=doc_type,
        days=max(base, 1),
        depends_on_third_party=doc_type in THIRD_PARTY_DOCUMENTS,
        country_adjusted=adjusted,
        notes=notes.strip(),
    )


def submission_deadline(
    cycle_deadline: Any,
    *,
    buffer_days: int = DEFAULT_SUBMISSION_BUFFER_DAYS,
) -> Any:
    """The internal deadline: the cycle deadline minus a safety buffer."""
    from datetime import datetime, timedelta, timezone

    if cycle_deadline is None:
        return None
    if isinstance(cycle_deadline, datetime):
        if cycle_deadline.tzinfo is None:
            cycle_deadline = cycle_deadline.replace(tzinfo=timezone.utc)
        return cycle_deadline - timedelta(days=buffer_days)
    return cycle_deadline
