"""Tests for Unlock Paths, the Smart Question Engine, conflict resolution and
cycle prediction.
"""

from __future__ import annotations

from datetime import date

import pytest

from scholarmind.eligibility.engine import (
    Comparator,
    EligibilityEngine,
    OverallStatus,
    Rule,
    RuleComparability,
)
from scholarmind.eligibility.questions import (
    coverage_summary,
    next_question,
    rank_questions,
)
from scholarmind.eligibility.unlock import CycleRules, compute_unlock_paths, describe_unlock_paths
from scholarmind.freshness.conflicts import SourceValue, resolve_conflict, summarise_sources
from scholarmind.normalization.prediction import HistoricalCycle, predict_next_cycle


def ielts_rule(score: float) -> Rule:
    return Rule(
        id=f"rule_ielts_{score}",
        kind="language",
        subject="ielts",
        comparator=Comparator.GTE,
        value=score,
        comparability=RuleComparability.MANDATORY,
        rule_text=f"Applicants must have an IELTS score of {score} or above.",
        evidence_ids=(f"ev_ielts_{score}",),
    )


def nationality_rule() -> Rule:
    return Rule(
        id="rule_nationality",
        kind="nationality",
        subject="nationality",
        comparator=Comparator.IN,
        value=["NGA"],
        comparability=RuleComparability.MANDATORY,
        rule_text="Open to Nigerian nationals.",
        evidence_ids=("ev_nationality",),
    )


def test_unlock_path_detects_the_english_test_improvement() -> None:
    cycles = [CycleRules(cycle_id="c1", rules=[nationality_rule(), ielts_rule(7.0)])]
    profile = {"nationality": "NGA", "ielts": 6.0}

    paths = compute_unlock_paths(profile=profile, cycles=cycles)

    assert paths
    best = paths[0]
    assert best.subject == "ielts"
    assert best.unlocked_cycle_ids == ["c1"]
    assert "IELTS 7.0" in best.label
    assert best.rule_ids_affected
    assert best.effort_note


def test_unlock_path_reports_the_smallest_sufficient_improvement() -> None:
    cycles = [CycleRules(cycle_id="c1", rules=[ielts_rule(6.5)])]
    profile = {"ielts": 6.0}
    paths = compute_unlock_paths(profile=profile, cycles=cycles)
    assert paths[0].to_value == 6.5


def test_no_unlock_path_when_nothing_changes() -> None:
    cycles = [CycleRules(cycle_id="c1", rules=[nationality_rule()])]
    profile = {"nationality": "NGA"}
    assert compute_unlock_paths(profile=profile, cycles=cycles) == []
    assert "No single profile change" in describe_unlock_paths([])


def test_no_unlock_is_claimed_when_another_mandatory_rule_still_fails() -> None:
    """A path is only offered when the whole cycle becomes eligible."""
    cycles = [
        CycleRules(
            cycle_id="c1",
            rules=[ielts_rule(7.0), nationality_rule()],
        )
    ]
    profile = {"ielts": 6.0, "nationality": "GHA"}
    assert compute_unlock_paths(profile=profile, cycles=cycles) == []


def test_unlock_paths_record_the_remaining_blockers() -> None:
    cycles = [
        CycleRules(cycle_id="c1", rules=[ielts_rule(7.0), nationality_rule()]),
        CycleRules(cycle_id="c2", rules=[ielts_rule(7.0)]),
    ]
    profile = {"ielts": 6.0, "nationality": "GHA"}
    paths = compute_unlock_paths(profile=profile, cycles=cycles)
    assert paths
    assert paths[0].unlocked_cycle_ids == ["c2"]
    assert paths[0].remaining_blockers


def test_smart_question_picks_the_most_impactful_field() -> None:
    engine = EligibilityEngine()
    profile = {"nationality": "NGA"}
    assessment = engine.evaluate(
        cycle_id="c1",
        rules=[
            Rule(id="r_ielts", kind="language", subject="ielts", comparator=Comparator.GTE, value=6.5, rule_text="IELTS 6.5"),
            Rule(id="r_gpa", kind="gpa", subject="gpa.min_overall", comparator=Comparator.GTE, value=3.0, rule_text="GPA 3.0"),
        ],
        profile=profile,
    )

    ranked = rank_questions(profile=profile, assessments={"c1": assessment})
    assert ranked
    assert ranked[0].field == "ielts"
    assert best_field(next_question(profile=profile, assessments={"c1": assessment}))


def best_field(question) -> str:
    return question.field if question else ""


def test_answered_fields_are_not_asked_again() -> None:
    engine = EligibilityEngine()
    profile = {"ielts": 7.0}
    assessment = engine.evaluate(
        cycle_id="c1",
        rules=[Rule(id="r_ielts", kind="language", subject="ielts", comparator=Comparator.GTE, value=6.5, rule_text="IELTS")],
        profile=profile,
    )
    ranked = rank_questions(profile=profile, assessments={"c1": assessment})
    assert all(question.field != "ielts" for question in ranked)


def test_coverage_summary_reports_unknown_rules() -> None:
    engine = EligibilityEngine()
    assessment = engine.evaluate(
        cycle_id="c1",
        rules=[Rule(id="r_ielts", kind="language", subject="ielts", comparator=Comparator.GTE, value=6.5, rule_text="IELTS")],
        profile={},
    )
    summary = coverage_summary(profile={}, assessments={"c1": assessment})
    assert summary["rules_unknown"] == 1
    assert summary["resolution_rate"] == 0.0


def test_conflict_prefers_the_higher_trust_source_but_flags_material_fields() -> None:
    resolution = resolve_conflict(
        field_name="deadline_at",
        sources=[
            SourceValue(source_document_id="s_funder", value="2026-11-12", trust_tier="official_primary"),
            SourceValue(source_document_id="s_uni", value="2026-11-20", trust_tier="official_secondary"),
        ],
    )
    assert resolution is not None
    assert resolution.proposed_value == "2026-11-12"
    assert resolution.proposed_source_document_id == "s_funder"
    assert resolution.requires_review is True


def test_conflict_with_equal_trust_requires_review() -> None:
    resolution = resolve_conflict(
        field_name="process",
        sources=[
            SourceValue(source_document_id="a", value="x", trust_tier="official_primary"),
            SourceValue(source_document_id="b", value="y", trust_tier="official_primary"),
        ],
    )
    assert resolution is not None
    assert resolution.requires_review is True
    assert "same trust tier" in resolution.reason


def test_no_conflict_when_sources_agree() -> None:
    resolution = resolve_conflict(
        field_name="deadline_at",
        sources=[
            SourceValue(source_document_id="a", value="2026-11-12", trust_tier="official_primary"),
            SourceValue(source_document_id="b", value="2026-11-12", trust_tier="official_secondary"),
        ],
    )
    assert resolution is None


def test_conflict_sources_are_summarised_by_trust() -> None:
    summary = summarise_sources(
        [
            SourceValue(source_document_id="a", value="x", trust_tier="aggregator"),
            SourceValue(source_document_id="b", value="y", trust_tier="official_primary"),
        ]
    )
    assert summary[0]["source_document_id"] == "b"
    assert summary[0]["rank"] > summary[1]["rank"]


def test_cycle_prediction_needs_at_least_two_past_cycles() -> None:
    assert predict_next_cycle([HistoricalCycle(intake_year=2026, opens_at=date(2026, 8, 4))]) is None


def test_cycle_prediction_estimates_the_median_opening_window() -> None:
    history = [
        HistoricalCycle(intake_year=2024, opens_at=date(2024, 8, 1), snapshot_id="s1"),
        HistoricalCycle(intake_year=2025, opens_at=date(2025, 8, 5), snapshot_id="s2"),
        HistoricalCycle(intake_year=2026, opens_at=date(2026, 8, 3), snapshot_id="s3"),
    ]
    prediction = predict_next_cycle(history, target_year=2027)

    assert prediction is not None
    assert prediction.predicted_intake_year == 2027
    assert prediction.predicted_open_date.month == 8
    assert prediction.is_estimate is True
    assert "estimate" in prediction.display().lower()
    assert prediction.supporting_snapshot_ids == ["s1", "s2", "s3"]


def test_cycle_prediction_never_claims_certainty() -> None:
    history = [
        HistoricalCycle(intake_year=2024, opens_at=date(2024, 1, 1)),
        HistoricalCycle(intake_year=2025, opens_at=date(2025, 6, 1)),
    ]
    prediction = predict_next_cycle(history, target_year=2026)
    assert prediction is not None
    assert prediction.confidence == "low"
    assert "not an announced date" in prediction.notes.lower()
