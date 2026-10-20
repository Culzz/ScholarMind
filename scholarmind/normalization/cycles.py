"""Cycle normalisation.

A scholarship award persists across years; each application round is a cycle
with its own dates, rules and funding. This module turns raw mentions of intake
years and dates into cycle records, and decides which cycle is the current one.

Two rules matter:

* A cycle with no known deadline has status ``undetermined`` — never ``open``.
* ``cycle_predictions`` (estimates) are never used here; only confirmed
  snapshots may contribute a cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence

from scholarmind.extraction.schema import Fact
from scholarmind.normalization.dates import cycle_status, deadline_is_open, days_until

YEAR_RE = re.compile(r"\b(20\d{2})\b")



def _as_date(value: Any) -> date | None:
    """Coerce an ISO date string into a date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


@dataclass
class NormalisedCycle:
    """A cycle ready for persistence."""

    intake_year: int
    cycle_label: str | None = None
    opens_at: date | None = None
    opens_at_precision: str = "unknown"
    deadline_at: Any = None
    deadline_timezone: str | None = None
    deadline_raw_text: str | None = None
    deadline_precision: str = "unknown"
    status: str = "undetermined"
    is_current: bool = False
    notes: str | None = None
    source_fact_indexes: list[int] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "intake_year": self.intake_year,
            "cycle_label": self.cycle_label,
            "opens_at": self.opens_at.isoformat() if self.opens_at else None,
            "opens_at_precision": self.opens_at_precision,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "deadline_timezone": self.deadline_timezone,
            "deadline_raw_text": self.deadline_raw_text,
            "deadline_precision": self.deadline_precision,
            "status": self.status,
            "is_current": self.is_current,
        }


def detect_intake_years(text: str, *, default_year: int | None = None) -> list[int]:
    """Years mentioned in the text, most likely intake years first."""
    years = sorted({int(match) for match in YEAR_RE.findall(text)})
    if default_year and default_year not in years:
        years.append(default_year)
    return years


def build_cycles(
    facts: Sequence[Fact],
    *,
    text: str,
    default_intake_year: int | None = None,
    now: Any = None,
) -> list[NormalisedCycle]:
    """Build cycle records from extracted deadline and opening-date facts."""
    years = detect_intake_years(text, default_year=default_intake_year)
    # The intake year is the one the corpus targets, not simply the first year
    # that appears on the page (a page usually mentions the current year first).
    if default_intake_year:
        primary_year = default_intake_year
    elif years:
        primary_year = max(years)
    else:
        primary_year = 0

    deadlines = [fact for fact in facts if fact.claim_type.value == "deadline"]
    openings = [fact for fact in facts if fact.claim_type.value == "opening_date"]

    cycle = NormalisedCycle(intake_year=primary_year)

    if deadlines:
        fact = deadlines[0]
        normalised = fact.normalized_value or {}
        cycle.deadline_at = _as_date(normalised.get("value"))
        cycle.deadline_raw_text = fact.text
        cycle.deadline_precision = normalised.get("precision", "unknown")
        cycle.deadline_timezone = normalised.get("timezone")
        cycle.source_fact_indexes.append(facts.index(fact))

    if openings:
        fact = openings[0]
        normalised = fact.normalized_value or {}
        cycle.opens_at = _as_date(normalised.get("value"))
        cycle.opens_at_precision = normalised.get("precision", "unknown")
        cycle.source_fact_indexes.append(facts.index(fact))

    cycle.status = cycle_status(cycle.deadline_at, cycle.opens_at, now=now)
    cycle.is_current = cycle.status in ("open", "upcoming", "undetermined")

    cycles = [cycle]

    # Earlier years mentioned on the same page become historical cycles. Their
    # dates are not derivable from this page, so they stay undetermined.
    for year in years[1:]:
        if year >= primary_year:
            continue
        cycles.append(
            NormalisedCycle(
                intake_year=year,
                status="closed",
                is_current=False,
                notes="Year mentioned on the page; specific cycle dates were not stated in this capture.",
            )
        )
    return cycles


def choose_current_cycles(cycles: Iterable[NormalisedCycle]) -> list[NormalisedCycle]:
    """Return the cycle(s) the UI should treat as current.

    A single cycle is current when one exists. If several are marked current,
    only those with a known deadline are kept, and the ambiguity is recorded by
    the caller rather than resolved silently.
    """
    candidates = [cycle for cycle in cycles if cycle.is_current]
    with_deadline = [cycle for cycle in candidates if cycle.deadline_at is not None]
    if len(with_deadline) == 1:
        return with_deadline
    if len(with_deadline) > 1:
        return with_deadline
    return candidates


def describe_cycle(cycle: NormalisedCycle, *, now: Any = None) -> dict[str, Any]:
    """Human-facing summary used by the API and the planner."""
    remaining = days_until(cycle.deadline_at, now=now)
    return {
        "intake_year": cycle.intake_year,
        "status": cycle.status,
        "deadline": cycle.deadline_at.isoformat() if cycle.deadline_at else None,
        "deadline_raw_text": cycle.deadline_raw_text,
        "deadline_precision": cycle.deadline_precision,
        "days_remaining": remaining,
        "is_open": deadline_is_open(cycle.deadline_at, now=now),
        "notes": cycle.notes,
    }
