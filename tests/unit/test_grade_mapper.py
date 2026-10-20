"""Tests for the grade mapper.

The grade mapper is the component that decides whether a student's African
qualification satisfies a funder's stated requirement. It must be conservative:
never over-credit a student, and never silently claim an equivalence.
"""

from __future__ import annotations

import pytest

from scholarmind.normalization.grades import (
    GradeRequirement,
    GradeScale,
    convert_grade,
    meets_requirement,
    parse_requirement,
)


def test_same_scale_conversion_is_exact() -> None:
    conversion = convert_grade(4.2, GradeScale.CGPA_5, GradeScale.CGPA_5)
    assert conversion.target_value == 4.2
    assert conversion.is_exact_match


def test_percentage_to_cgpa5_is_conservative() -> None:
    conversion = convert_grade(72, GradeScale.PERCENTAGE, GradeScale.CGPA_5)
    # 72% anchors at the 70th percentile -> First Class band -> 4.5 on a 5.0 CGPA
    assert conversion.target_value == 4.5
    assert conversion.is_exact_match is False
    assert "lower bound" in conversion.equivalence_rule


def test_cgpa5_to_percentage() -> None:
    conversion = convert_grade(4.6, GradeScale.CGPA_5, GradeScale.PERCENTAGE)
    assert conversion.target_value == 70.0


def test_gpa4_to_percentage() -> None:
    conversion = convert_grade(3.8, GradeScale.GPA_4, GradeScale.PERCENTAGE)
    assert conversion.target_value == 85.0


def test_credit_to_cgpa5() -> None:
    conversion = convert_grade(3.7, GradeScale.CREDIT, GradeScale.CGPA_5)
    assert conversion.target_value == 4.5


@pytest.mark.parametrize(
    "text,scale,is_categorical",
    [
        ("Applicants must hold at least a Second Class Upper degree", GradeScale.SECOND_CLASS_UPPER, True),
        ("Minimum qualification: First Class", GradeScale.FIRST_CLASS, True),
        ("A minimum CGPA of 4.0 on a 5.0 scale is required", GradeScale.CGPA_5, False),
        ("Candidates must have at least 60%", GradeScale.PERCENTAGE, False),
        ("Minimum grade of 65%", GradeScale.PERCENTAGE, False),
    ],
)
def test_requirement_parsing(text: str, scale: GradeScale, is_categorical: bool) -> None:
    requirement = parse_requirement(text)
    assert requirement.scale is scale
    assert requirement.is_categorical is is_categorical


def test_requirement_parsing_reports_unparseable_requirements() -> None:
    requirement = parse_requirement("Applicants must have an excellent academic record.")
    assert requirement.min_value is None
    status, explanation = meets_requirement(4.0, GradeScale.CGPA_5, requirement)
    assert status == "needs_review"
    assert "could not be parsed" in explanation


def test_same_scale_comparison_is_definitive() -> None:
    requirement = GradeRequirement(min_value=4.0, scale=GradeScale.CGPA_5, raw_text="minimum CGPA 4.0 on 5.0 scale")
    status, _ = meets_requirement(4.3, GradeScale.CGPA_5, requirement)
    assert status == "satisfied"
    status, _ = meets_requirement(3.2, GradeScale.CGPA_5, requirement)
    assert status == "not_satisfied"


def test_categorical_requirement_on_a_different_scale_uses_bands() -> None:
    requirement = GradeRequirement(
        min_value=None, scale=GradeScale.SECOND_CLASS_UPPER, raw_text="Second Class Upper", is_categorical=True
    )
    status, explanation = meets_requirement(70, GradeScale.PERCENTAGE, requirement)
    assert status == "satisfied"
    assert "First Class" in explanation

    status, _ = meets_requirement(45, GradeScale.PERCENTAGE, requirement)
    assert status == "not_satisfied"


def test_categorical_requirement_on_the_same_scale_is_definitive() -> None:
    requirement = GradeRequirement(
        min_value=None, scale=GradeScale.FIRST_CLASS, raw_text="First Class", is_categorical=True
    )
    status, _ = meets_requirement(4.8, GradeScale.CGPA_5, requirement)
    assert status == "satisfied"
    status, _ = meets_requirement(3.4, GradeScale.CGPA_5, requirement)
    assert status == "not_satisfied"


def test_cross_scale_numeric_comparison_never_claims_certainty() -> None:
    requirement = GradeRequirement(min_value=4.0, scale=GradeScale.CGPA_5, raw_text="minimum 4.0")
    status, explanation = meets_requirement(65, GradeScale.PERCENTAGE, requirement)
    assert status in ("satisfied", "not_satisfied")
    assert "approximate" in explanation
    assert "confirm it with the scholarship office" in explanation


def test_conversion_never_exceeds_the_band() -> None:
    """A conversion must never award more than the conservative lower bound."""
    for percentage in range(40, 101, 5):
        conversion = convert_grade(percentage, GradeScale.PERCENTAGE, GradeScale.CGPA_5)
        assert conversion.target_value <= 4.5
        assert conversion.target_value >= 0.0
