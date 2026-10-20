"""Unit tests for the eligibility engine.

The invariants tested here are the ones that protect students from false
positives: a missing fact must never read as a satisfied requirement.
"""

from __future__ import annotations

import pytest

from scholarmind.eligibility.engine import (
    Comparator,
    EligibilityEngine,
    OverallStatus,
    RuleComparability,
    Rule,
    Verdict,
    summarize,
)


def make_rule(**overrides) -> Rule:
    defaults = dict(
        kind="gpa",
        subject="gpa.min_overall",
        comparator=Comparator.GTE,
        value=3.0,
        comparability=RuleComparability.MANDATORY,
        rule_text="Applicants must hold at least a 3.0 GPA.",
        evidence_ids=("ev_1",),
    )
    defaults.update(overrides)
    return Rule(**defaults)  # type: ignore[arg-type]


def test_missing_fact_is_unknown_not_satisfied() -> None:
    engine = EligibilityEngine()
    assessment = engine.evaluate(cycle_id="cycle-1", rules=[make_rule()], profile={})
    result = assessment.results[0]

    assert result.verdict is Verdict.UNKNOWN
    assert result.missing_field == "gpa.min_overall"
    assert assessment.overall_status is OverallStatus.UNKNOWN


def test_none_valued_fact_is_treated_as_missing() -> None:
    engine = EligibilityEngine()
    assessment = engine.evaluate(cycle_id="c", rules=[make_rule()], profile={"gpa": None})
    assert assessment.results[0].verdict is Verdict.UNKNOWN


def test_satisfied_rule_marks_eligible() -> None:
    engine = EligibilityEngine()
    assessment = engine.evaluate(cycle_id="c", rules=[make_rule()], profile={"gpa": 3.6})
    assert assessment.results[0].verdict is Verdict.SATISFIED
    assert assessment.overall_status is OverallStatus.ELIGIBLE


def test_failing_mandatory_rule_marks_not_eligible() -> None:
    engine = EligibilityEngine()
    assessment = engine.evaluate(cycle_id="c", rules=[make_rule()], profile={"gpa": 2.1})
    assert assessment.results[0].verdict is Verdict.NOT_SATISFIED
    assert assessment.overall_status is OverallStatus.NOT_ELIGIBLE


def test_ambiguous_rule_requires_review() -> None:
    engine = EligibilityEngine()
    rule = make_rule(ambiguous=True, rule_text="Applicants should preferably hold strong grades.")
    assessment = engine.evaluate(cycle_id="c", rules=[rule], profile={"gpa": 3.6})
    assert assessment.results[0].verdict is Verdict.NEEDS_REVIEW
    assert assessment.overall_status is OverallStatus.NEEDS_REVIEW


def test_optional_unknown_yields_likely_eligible() -> None:
    engine = EligibilityEngine()
    rule = make_rule(comparability=RuleComparability.OPTIONAL)
    assessment = engine.evaluate(cycle_id="c", rules=[rule], profile={})
    assert assessment.overall_status is OverallStatus.LIKELY_ELIGIBLE


def test_missing_fields_lists_every_unknown_subject() -> None:
    engine = EligibilityEngine()
    rules = [
        make_rule(subject="gpa.min_overall"),
        make_rule(subject="age.max", comparator=Comparator.LTE, value=30),
    ]
    assessment = engine.evaluate(cycle_id="c", rules=rules, profile={})
    assert assessment.missing_fields == ["gpa.min_overall", "age.max"]


def test_nationality_rule_reads_profile_fallbacks() -> None:
    engine = EligibilityEngine()
    rule = Rule(
        kind="nationality",
        subject="nationality",
        comparator=Comparator.IN,
        value=["NGA", "GHA"],
        rule_text="Open to Nigerian and Ghanaian nationals.",
    )
    assessment = engine.evaluate(cycle_id="c", rules=[rule], profile={"residency": "NGA"})
    assert assessment.results[0].verdict is Verdict.SATISFIED


def test_non_numeric_comparison_yields_needs_review() -> None:
    engine = EligibilityEngine()
    rule = make_rule(comparator=Comparator.GTE, value=3.0)
    assessment = engine.evaluate(cycle_id="c", rules=[rule], profile={"gpa": "first class"})
    assert assessment.results[0].verdict is Verdict.NEEDS_REVIEW


def test_engine_is_deterministic_under_rule_permutation() -> None:
    engine = EligibilityEngine()
    rules = [
        make_rule(subject="gpa.min_overall"),
        make_rule(subject="age.max", comparator=Comparator.LTE, value=30),
    ]
    profile = {"gpa": 3.4, "age": 24}
    first = engine.evaluate(cycle_id="c", rules=rules, profile=profile)
    second = engine.evaluate(cycle_id="c", rules=list(reversed(rules)), profile=profile)

    assert [r.verdict for r in first.results] == [r.verdict for r in reversed(second.results)]
    assert first.overall_status is second.overall_status


def test_every_verdict_carries_a_reason() -> None:
    engine = EligibilityEngine()
    rules = [make_rule(), make_rule(subject="age.max", comparator=Comparator.LTE, value=30)]
    assessment = engine.evaluate(cycle_id="c", rules=rules, profile={"gpa": 3.4})
    for result in assessment.results:
        assert result.reason
        assert result.to_dict()["evidence_ids"]


def test_summarize_shape() -> None:
    engine = EligibilityEngine()
    assessment = engine.evaluate(cycle_id="c", rules=[make_rule()], profile={})
    summary = summarize(assessment)
    assert summary["overall_status"] == "unknown"
    assert summary["unknowns"] == 1
    assert summary["missing_fields"] == ["gpa.min_overall"]


@pytest.mark.parametrize(
    "comparator,value,fact,expected",
    [
        (Comparator.EQUALS, "BSc", "BSc", Verdict.SATISFIED),
        (Comparator.EQUALS, "BSc", "PhD", Verdict.NOT_SATISFIED),
        (Comparator.IN, ["masters", "phd"], "phd", Verdict.SATISFIED),
        (Comparator.NOT_IN, ["masters"], "phd", Verdict.SATISFIED),
        (Comparator.GTE, 30, 34, Verdict.SATISFIED),
        (Comparator.LTE, 30, 34, Verdict.NOT_SATISFIED),
        (Comparator.BETWEEN, [3.0, 4.0], 3.5, Verdict.SATISFIED),
        (Comparator.BETWEEN, [3.0, 4.0], 4.5, Verdict.NOT_SATISFIED),
        (Comparator.CONTAINS, "english", "english-medium degree", Verdict.SATISFIED),
    ],
)
def test_comparator_matrix(comparator, value, fact, expected) -> None:
    engine = EligibilityEngine()
    rule = Rule(kind="other", subject="fact", comparator=comparator, value=value, rule_text="r")
    assessment = engine.evaluate(cycle_id="c", rules=[rule], profile={"fact": fact})
    assert assessment.results[0].verdict is expected
