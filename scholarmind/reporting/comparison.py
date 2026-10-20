"""Side-by-side comparison of scholarships.

A comparison is only useful if it is honest about what is unknown. This module
builds a comparison matrix in which every cell carries a state
(``confirmed`` / ``excluded`` / ``conditional`` / ``unknown`` / ``unresolved``),
and never fills a gap with a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

COVERAGE_STATES = ("included", "excluded", "conditional", "unknown")


@dataclass
class ComparisonCell:
    """One cell of the comparison matrix."""

    field: str
    value: Any = None
    state: str = "unknown"
    source: str | None = None
    checked_at: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "state": self.state,
            "source": self.source,
            "checked_at": self.checked_at,
            "note": self.note,
        }


@dataclass
class ComparisonColumn:
    """One scholarship in the comparison."""

    scholarship_id: str
    name: str
    cycle_id: str | None = None
    deadline: str | None = None
    deadline_state: str = "unknown"
    source_url: str | None = None
    source_checked_at: str | None = None
    cells: dict[str, ComparisonCell] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scholarship_id": self.scholarship_id,
            "name": self.name,
            "cycle_id": self.cycle_id,
            "deadline": self.deadline,
            "deadline_state": self.deadline_state,
            "source_url": self.source_url,
            "source_checked_at": self.source_checked_at,
            "cells": {key: cell.to_dict() for key, cell in self.cells.items()},
        }


@dataclass
class Comparison:
    """A full comparison across several scholarships."""

    columns: list[ComparisonColumn] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": list(self.fields),
            "columns": [column.to_dict() for column in self.columns],
            "conflicts": list(self.conflicts),
            "notes": list(self.notes),
        }


def build_comparison(
    *,
    columns: Sequence[ComparisonColumn],
    fields: Sequence[str],
    conflicts: Sequence[dict[str, Any]] = (),
) -> Comparison:
    """Assemble a comparison, flagging rows where the columns disagree."""
    comparison = Comparison(columns=list(columns), fields=list(fields), conflicts=list(conflicts))

    for field_name in fields:
        states = {
            column.cells[field_name].state
            for column in columns
            if field_name in column.cells
        }
        if len(states) > 1 and not comparison.conflicts:
            comparison.notes.append(
                f"'{field_name}' differs across the compared scholarships - the rows are not "
                "comparable on this field."
            )
    return comparison


def funding_row(
    component: str,
    coverage: str,
    *,
    value: Any = None,
    source: str | None = None,
    checked_at: str | None = None,
) -> ComparisonCell:
    """Build a funding cell with a validated coverage state."""
    state = coverage if coverage in COVERAGE_STATES else "unknown"
    return ComparisonCell(
        field=component,
        value=value,
        state=state,
        source=source,
        checked_at=checked_at,
    )


def unknown_fields(count: int) -> list[str]:
    """How many fields are unknown across a comparison (surfaced prominently)."""
    return ["unknown"] * count
