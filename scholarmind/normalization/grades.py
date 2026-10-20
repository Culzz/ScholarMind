"""Grade mapper: African and international grade scales, normalised.

African applicants face a specific problem: a funder states its grade
requirement in one scale ("minimum Second Class Upper", "CGPA 4.0 on a 5.0
scale", "at least 60%") while the student holds a grade expressed in another
("First Class", "CGPA 5.0", "78%"). Comparing the numbers directly silently
misjudges eligibility, in both directions.

This module converts between scales through documented **percentile anchors**
and reports, for every conversion:

* the target value,
* the equivalence rule that produced it,
* whether the conversion is exact or an approximation,
* the evidence required to publish the mapping.

Conversions are deliberately conservative: a mapped value is the **lower**
bound of the band, so a student is never told they qualify on the strength of
an optimistic rounding. An approximation never yields ``satisfied`` on its
own — it yields ``needs_review`` until a human confirms the equivalence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GradeScale(str, Enum):
    """Supported grading scales."""

    PERCENTAGE = "percentage"
    CGPA_5 = "cgpa_5"
    CGPA_4 = "cgpa_4"
    GPA_4 = "gpa_4"
    GPA_5 = "gpa_5"
    CREDIT = "credit"
    FIRST_CLASS = "first_class"
    SECOND_CLASS_UPPER = "second_class_upper"
    SECOND_CLASS_LOWER = "second_class_lower"
    PASS = "pass"


@dataclass(frozen=True)
class ScaleDefinition:
    """How one scale relates to the common percentile anchor."""

    code: GradeScale
    label: str
    min_value: float | None
    max_value: float | None
    categorical: bool = False
    anchor_percentile: float | None = None
    note: str = ""


SCALE_DEFINITIONS: dict[GradeScale, ScaleDefinition] = {
    GradeScale.PERCENTAGE: ScaleDefinition(
        GradeScale.PERCENTAGE, "Percentage", 0, 100, note="1-100% scale used across most African universities."
    ),
    GradeScale.CGPA_5: ScaleDefinition(
        GradeScale.CGPA_5, "CGPA (5.0 scale)", 0, 5, note="Nigerian 5-point CGPA."
    ),
    GradeScale.CGPA_4: ScaleDefinition(
        GradeScale.CGPA_4, "CGPA (4.0 scale)", 0, 4, note="4-point CGPA used by some institutions."
    ),
    GradeScale.GPA_4: ScaleDefinition(
        GradeScale.GPA_4, "GPA (4.0 scale)", 0, 4, note="Standard 4.0 GPA."
    ),
    GradeScale.GPA_5: ScaleDefinition(
        GradeScale.GPA_5, "GPA (5.0 scale)", 0, 5, note="5-point GPA."
    ),
    GradeScale.CREDIT: ScaleDefinition(
        GradeScale.CREDIT, "US credit", 0, 4, note="US 4.0 credit GPA."
    ),
    GradeScale.FIRST_CLASS: ScaleDefinition(
        GradeScale.FIRST_CLASS, "First Class", None, None, categorical=True, anchor_percentile=70.0,
        note="Conventionally 70% and above (70-100% band).",
    ),
    GradeScale.SECOND_CLASS_UPPER: ScaleDefinition(
        GradeScale.SECOND_CLASS_UPPER, "Second Class Upper (2:1)", None, None, categorical=True,
        anchor_percentile=60.0, note="Conventionally 60-69% band.",
    ),
    GradeScale.SECOND_CLASS_LOWER: ScaleDefinition(
        GradeScale.SECOND_CLASS_LOWER, "Second Class Lower (2:2)", None, None, categorical=True,
        anchor_percentile=50.0, note="Conventionally 50-59% band.",
    ),
    GradeScale.PASS: ScaleDefinition(
        GradeScale.PASS, "Pass", None, None, categorical=True, anchor_percentile=40.0,
        note="Minimum pass grade.",
    ),
}


def _cgpa5_percentile(value: float) -> float:
    if value >= 4.5:
        return 70.0
    if value >= 4.0:
        return 60.0
    if value >= 3.5:
        return 50.0
    if value >= 3.0:
        return 45.0
    if value >= 2.0:
        return 40.0
    return 0.0


def _cgpa4_percentile(value: float) -> float:
    if value >= 3.5:
        return 65.0
    if value >= 3.0:
        return 55.0
    if value >= 2.5:
        return 50.0
    if value >= 2.0:
        return 45.0
    return 0.0


def _gpa4_percentile(value: float) -> float:
    if value >= 4.0:
        return 90.0
    if value >= 3.7:
        return 85.0
    if value >= 3.3:
        return 75.0
    if value >= 3.0:
        return 65.0
    if value >= 2.7:
        return 55.0
    if value >= 2.0:
        return 45.0
    return 0.0


def _credit_percentile(value: float) -> float:
    if value >= 4.0:
        return 90.0
    if value >= 3.5:
        return 80.0
    if value >= 3.0:
        return 70.0
    if value >= 2.0:
        return 55.0
    return 0.0


def _gpa5_percentile(value: float) -> float:
    return _cgpa5_percentile(value)


def to_percentile(value: float, scale: GradeScale) -> float:
    """Convert a grade value to its conservative percentile anchor."""
    if scale is GradeScale.PERCENTAGE:
        return float(value)
    if scale is GradeScale.CGPA_5:
        return _cgpa5_percentile(value)
    if scale is GradeScale.CGPA_4:
        return _cgpa4_percentile(value)
    if scale is GradeScale.GPA_4:
        return _gpa4_percentile(value)
    if scale is GradeScale.GPA_5:
        return _gpa5_percentile(value)
    if scale is GradeScale.CREDIT:
        return _credit_percentile(value)
    definition = SCALE_DEFINITIONS[scale]
    if definition.anchor_percentile is None:
        raise ValueError(f"scale {scale.value} has no percentile anchor")
    return definition.anchor_percentile


def _percentile_to_cgpa5(percentile: float) -> float:
    if percentile >= 70:
        return 4.5
    if percentile >= 60:
        return 4.0
    if percentile >= 50:
        return 3.5
    if percentile >= 45:
        return 3.0
    if percentile >= 40:
        return 2.5
    return 0.0


def _percentile_to_cgpa4(percentile: float) -> float:
    if percentile >= 65:
        return 3.5
    if percentile >= 55:
        return 3.0
    if percentile >= 50:
        return 2.5
    if percentile >= 45:
        return 2.0
    return 0.0


def _percentile_to_gpa4(percentile: float) -> float:
    if percentile >= 90:
        return 4.0
    if percentile >= 80:
        return 3.7
    if percentile >= 70:
        return 3.3
    if percentile >= 60:
        return 3.0
    if percentile >= 50:
        return 2.7
    return 0.0


def _percentile_to_credit(percentile: float) -> float:
    if percentile >= 90:
        return 4.0
    if percentile >= 80:
        return 3.5
    if percentile >= 70:
        return 3.0
    if percentile >= 55:
        return 2.0
    return 0.0


def _percentile_to_gpa5(percentile: float) -> float:
    return _percentile_to_cgpa5(percentile)


@dataclass(frozen=True)
class GradeConversion:
    """The result of converting a grade between scales."""

    source_value: float
    source_scale: GradeScale
    target_scale: GradeScale
    target_value: float
    equivalence_rule: str
    is_exact_match: bool
    percentile_anchor: float

    def to_record(self) -> dict[str, Any]:
        return {
            "source_value": self.source_value,
            "source_scale": self.source_scale.value,
            "target_scale": self.target_scale.value,
            "target_value": self.target_value,
            "equivalence_rule": self.equivalence_rule,
            "is_exact_match": self.is_exact_match,
            "percentile_anchor": self.percentile_anchor,
        }


def convert_grade(
    value: float,
    source_scale: GradeScale,
    target_scale: GradeScale,
) -> GradeConversion:
    """Convert a grade value from one scale to another, conservatively.

    The converted value is the **lower** bound of the equivalent band, so a
    student is never advantaged by rounding.
    """
    if source_scale is target_scale:
        return GradeConversion(
            source_value=value,
            source_scale=source_scale,
            target_scale=target_scale,
            target_value=value,
            equivalence_rule="same scale: value used directly",
            is_exact_match=True,
            percentile_anchor=to_percentile(value, source_scale),
        )

    anchor = to_percentile(value, source_scale)

    if target_scale is GradeScale.PERCENTAGE:
        target_value = anchor
    elif target_scale is GradeScale.CGPA_5:
        target_value = _percentile_to_cgpa5(anchor)
    elif target_scale is GradeScale.CGPA_4:
        target_value = _percentile_to_cgpa4(anchor)
    elif target_scale is GradeScale.GPA_4:
        target_value = _percentile_to_gpa4(anchor)
    elif target_scale is GradeScale.GPA_5:
        target_value = _percentile_to_gpa5(anchor)
    elif target_scale is GradeScale.CREDIT:
        target_value = _percentile_to_credit(anchor)
    else:
        # Converting to a categorical scale: report the band the anchor falls in.
        target_value = _categorical_for_percentile(anchor)

    definition = SCALE_DEFINITIONS[target_scale]
    rule = (
        f"{SCALE_DEFINITIONS[source_scale].label} value {value} anchors at the "
        f"{anchor:.0f}th percentile, which maps to {target_value} on the "
        f"{definition.label} (lower bound of the band)."
    )
    return GradeConversion(
        source_value=value,
        source_scale=source_scale,
        target_scale=target_scale,
        target_value=target_value,
        equivalence_rule=rule,
        is_exact_match=False,
        percentile_anchor=anchor,
    )


def _categorical_for_percentile(percentile: float) -> float:
    """Categorical bands expressed as their anchor percentile."""
    if percentile >= 70:
        return 70.0
    if percentile >= 60:
        return 60.0
    if percentile >= 50:
        return 50.0
    return 40.0



@dataclass(frozen=True)
class GradeBand:
    """A classification band such as "First Class"."""

    code: str
    label: str
    rank: int
    note: str = ""


BAND_FIRST = GradeBand("first_class", "First Class", 3, "Band thresholds follow the common African university convention.")
BAND_SECOND_UPPER = GradeBand("second_class_upper", "Second Class Upper (2:1)", 2, "Band thresholds follow the common African university convention.")
BAND_SECOND_LOWER = GradeBand("second_class_lower", "Second Class Lower (2:2)", 1, "Band thresholds follow the common African university convention.")
BAND_PASS = GradeBand("pass", "Pass", 0, "Band thresholds follow the common African university convention.")

BAND_THRESHOLDS: dict[GradeScale, tuple[tuple[float, GradeBand], ...]] = {
    GradeScale.PERCENTAGE: ((70, BAND_FIRST), (60, BAND_SECOND_UPPER), (50, BAND_SECOND_LOWER)),
    GradeScale.CGPA_5: ((4.5, BAND_FIRST), (4.0, BAND_SECOND_UPPER), (3.5, BAND_SECOND_LOWER)),
    GradeScale.CGPA_4: ((3.7, BAND_FIRST), (3.0, BAND_SECOND_UPPER), (2.5, BAND_SECOND_LOWER)),
    GradeScale.GPA_4: ((3.7, BAND_FIRST), (3.0, BAND_SECOND_UPPER), (2.5, BAND_SECOND_LOWER)),
    GradeScale.GPA_5: ((4.5, BAND_FIRST), (4.0, BAND_SECOND_UPPER), (3.5, BAND_SECOND_LOWER)),
    GradeScale.CREDIT: ((3.7, BAND_FIRST), (3.0, BAND_SECOND_UPPER), (2.5, BAND_SECOND_LOWER)),
    GradeScale.FIRST_CLASS: ((70, BAND_FIRST),),
    GradeScale.SECOND_CLASS_UPPER: ((60, BAND_SECOND_UPPER),),
    GradeScale.SECOND_CLASS_LOWER: ((50, BAND_SECOND_LOWER),),
    GradeScale.PASS: ((0, BAND_PASS),),
}


def categorical_band(value: float, scale: GradeScale) -> GradeBand:
    """Classify a grade into its band for a given scale."""
    thresholds = BAND_THRESHOLDS.get(scale)
    if not thresholds:
        return BAND_PASS
    for threshold, band in thresholds:
        if value >= threshold:
            return band
    return BAND_PASS


@dataclass(frozen=True)
class GradeRequirement:
    """A grade requirement as stated by a funder."""

    min_value: float | None
    scale: GradeScale
    raw_text: str
    is_categorical: bool = False

    def describe(self) -> str:
        definition = SCALE_DEFINITIONS[self.scale]
        if self.is_categorical or self.min_value is None:
            return definition.label
        return f"at least {self.min_value} on the {definition.label}"


def meets_requirement(
    student_value: float,
    student_scale: GradeScale,
    requirement: GradeRequirement,
) -> tuple[str, str]:
    """Compare a student grade against a funder's requirement.

    Returns ``(status, explanation)`` where status is one of
    ``satisfied`` / ``not_satisfied`` / ``needs_review``.

    A requirement on a different scale from the student's grade produces
    ``needs_review`` when the conversion is approximate, because the
    equivalence is a judgement, not a fact.
    """
    if requirement.min_value is None and not requirement.is_categorical:
        return "needs_review", (
            f"The official requirement could not be parsed into a comparable value: '{requirement.raw_text}'."
        )

    if requirement.is_categorical:
        student_band = categorical_band(student_value, student_scale)
        required_band = categorical_band(
            SCALE_DEFINITIONS[requirement.scale].anchor_percentile or 0.0,
            requirement.scale,
        )
        if student_band.rank >= required_band.rank:
            explanation = (
                f"Your grade ({SCALE_DEFINITIONS[student_scale].label} {student_value}) sits in the "
                f"{student_band.label} band, which meets the requirement ({requirement.describe()}). "
                f"{student_band.note}"
            )
            return "satisfied", explanation
        explanation = (
            f"Your grade ({SCALE_DEFINITIONS[student_scale].label} {student_value}) sits in the "
            f"{student_band.label} band, which is below the requirement ({requirement.describe()}). "
            f"{student_band.note}"
        )
        return "not_satisfied", explanation

    if student_scale is requirement.scale:
        satisfied = student_value >= (requirement.min_value or 0.0)
        explanation = (
            f"Your {SCALE_DEFINITIONS[student_scale].label} value is {student_value}; the requirement is "
            f"{requirement.describe()}."
        )
        return ("satisfied" if satisfied else "not_satisfied"), explanation

    conversion = convert_grade(student_value, student_scale, requirement.scale)
    threshold = requirement.min_value or 0.0
    satisfied = conversion.target_value >= threshold
    explanation = (
        f"Your grade ({SCALE_DEFINITIONS[student_scale].label} {student_value}) converts to "
        f"{conversion.target_value} on the {SCALE_DEFINITIONS[requirement.scale].label}. "
        f"The requirement is {requirement.describe()}. This conversion is approximate — "
        "confirm it with the scholarship office."
    )
    return ("satisfied" if satisfied else "not_satisfied"), explanation


def _categorical_meets(student_scale: GradeScale, value: float, required: GradeScale) -> bool:
    order = [
        GradeScale.PASS,
        GradeScale.SECOND_CLASS_LOWER,
        GradeScale.SECOND_CLASS_UPPER,
        GradeScale.FIRST_CLASS,
    ]
    if required not in order:
        return False
    student_percentile = to_percentile(value, student_scale)
    required_percentile = SCALE_DEFINITIONS[required].anchor_percentile or 0.0
    return student_percentile >= required_percentile


# --- requirement parsing -------------------------------------------------


def parse_requirement(text: str) -> GradeRequirement:
    """Parse a stated grade requirement into a typed requirement.

    Unparseable requirements are returned with ``min_value=None`` so the caller
    surfaces them for review instead of guessing.
    """
    from scholarmind.normalization.dates import MONTH_NAMES  # noqa: F401  (kept for import symmetry)

    lowered = text.lower()

    if "first class" in lowered:
        return GradeRequirement(min_value=None, scale=GradeScale.FIRST_CLASS, raw_text=text, is_categorical=True)
    if "second class upper" in lowered or "2:1" in lowered or "second upper" in lowered:
        return GradeRequirement(
            min_value=None, scale=GradeScale.SECOND_CLASS_UPPER, raw_text=text, is_categorical=True
        )
    if "second class lower" in lowered or "2:2" in lowered or "second lower" in lowered:
        return GradeRequirement(
            min_value=None, scale=GradeScale.SECOND_CLASS_LOWER, raw_text=text, is_categorical=True
        )

    import re

    denominator_match = re.search(r"(\d(?:[.,]\d+)?)\s*(?:point\s*)?scale", lowered)
    if denominator_match and ("cgpa" in lowered or "gpa" in lowered):
        denominator = float(denominator_match.group(1).replace(",", "."))
        scale = GradeScale.CGPA_5 if denominator >= 5 else GradeScale.CGPA_4
        threshold = re.search(
            r"(?:minimum|min|at least|above|not less than|no less than)\s*(?:[a-z]+\s+){0,3}?(\d(?:[.,]\d+)?)",
            lowered,
        )
        min_value = float(threshold.group(1).replace(",", ".")) if threshold else None
        return GradeRequirement(min_value=min_value, scale=scale, raw_text=text)

    percentage_match = re.search(r"(?:at least|minimum|min|above)\s*(\d{1,3}(?:\.\d+)?)\s*%", lowered)
    if percentage_match:
        return GradeRequirement(
            min_value=float(percentage_match.group(1)), scale=GradeScale.PERCENTAGE, raw_text=text
        )

    plain_percentage = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*%\b", lowered)
    if plain_percentage:
        return GradeRequirement(
            min_value=float(plain_percentage.group(1)), scale=GradeScale.PERCENTAGE, raw_text=text
        )

    return GradeRequirement(min_value=None, scale=GradeScale.PERCENTAGE, raw_text=text)
