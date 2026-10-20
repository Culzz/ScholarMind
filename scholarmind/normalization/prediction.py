"""Cycle prediction: estimating the next application window.

Some funders publish a deadline every year but never announce the next cycle in
advance. Students still need to know when to start preparing, so the platform
estimates the next opening window from previous cycles.

The rules for predictions are strict:

* A prediction is an **estimate**, always labelled as one.
* A prediction is never stored as a fact and never used to answer "is this
  open?".
* A prediction is never used to satisfy an eligibility rule.
* Every prediction records the past snapshots it was derived from, so the
  estimate can be checked later.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

MINIMUM_CYCLES = 2


@dataclass(frozen=True)
class HistoricalCycle:
    """A past cycle with a known opening date."""

    intake_year: int
    opens_at: date
    closes_at: date | None = None
    snapshot_id: str | None = None

    def day_of_year(self) -> int:
        return self.opens_at.timetuple().tm_yday


@dataclass
class CyclePrediction:
    """An estimated next opening window."""

    predicted_intake_year: int
    predicted_open_date: date
    predicted_close_date: date | None
    method: str
    confidence: str
    supporting_snapshot_ids: list[str] = field(default_factory=list)
    is_estimate: bool = True
    notes: str = ""

    def to_record(self) -> dict[str, Any]:
        return {
            "predicted_intake_year": self.predicted_intake_year,
            "predicted_open_date": self.predicted_open_date.isoformat(),
            "predicted_close_date": self.predicted_close_date.isoformat() if self.predicted_close_date else None,
            "method": self.method,
            "confidence": self.confidence,
            "supporting_snapshot_ids": list(self.supporting_snapshot_ids),
            "is_estimate": self.is_estimate,
            "notes": self.notes,
        }

    def display(self) -> str:
        """How the estimate is presented to a student."""
        return (
            f"Estimated opening: around {self.predicted_open_date.strftime('%B %Y')} "
            f"(based on {self.confidence} confidence in past cycles). This is an estimate, "
            "not an announced date — check the official page before relying on it."
        )


def _confidence_from_spread(spread: int, count: int) -> str:
    if count >= 4 and spread <= 21:
        return "medium"
    if count >= 3 and spread <= 45:
        return "low"
    return "low"


def predict_next_cycle(
    history: Sequence[HistoricalCycle],
    *,
    target_year: int | None = None,
) -> CyclePrediction | None:
    """Estimate the next opening window from previous cycles.

    Returns ``None`` when there is not enough history to make an estimate —
    the platform does not guess from a single data point.
    """
    usable = [cycle for cycle in history if cycle.opens_at]
    if len(usable) < MINIMUM_CYCLES:
        return None

    years = sorted(cycle.intake_year for cycle in usable)
    next_year = target_year or (years[-1] + 1)

    day_of_years = [cycle.day_of_year() for cycle in usable]
    median_day = int(statistics.median(day_of_years))
    spread = max(day_of_years) - min(day_of_years)

    try:
        open_date = date(next_year, 1, 1) + timedelta(days=median_day - 1)
    except ValueError:  # pragma: no cover - 29 February in a non-leap year
        open_date = date(next_year, 3, 1)

    close_date = None
    durations = [
        (cycle.closes_at - cycle.opens_at).days
        for cycle in usable
        if cycle.closes_at is not None
    ]
    if durations:
        close_date = open_date + timedelta(days=int(statistics.median(durations)))

    return CyclePrediction(
        predicted_intake_year=next_year,
        predicted_open_date=open_date,
        predicted_close_date=close_date,
        method="median_day_of_year",
        confidence=_confidence_from_spread(spread, len(usable)),
        supporting_snapshot_ids=[cycle.snapshot_id for cycle in usable if cycle.snapshot_id],
        notes=(
            f"Estimated from {len(usable)} previous cycles "
            f"(opening dates varied by {spread} days). Not an announced date."
        ),
    )


def estimate_from_source_dates(
    dates: Sequence[date],
    *,
    target_year: int,
) -> CyclePrediction | None:
    """Estimate an opening date from a list of past opening dates."""
    history = [
        HistoricalCycle(intake_year=date.year, opens_at=date, snapshot_id=None) for date in dates
    ]
    return predict_next_cycle(history, target_year=target_year)
