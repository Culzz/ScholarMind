"""Tests for the application planner, exports and the transparent ranking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scholarmind.planning.export import plan_to_ics, plan_to_markdown, shortlist_to_csv
from scholarmind.planning.leadtimes import lead_time_for
from scholarmind.planning.plan import RequiredDocument, generate_plan, sort_tasks
from scholarmind.reporting.ranking import (
    DEFAULT_WEIGHTS,
    describe_weights,
    normalise_weights,
    rank_opportunities,
    score_opportunity,
    weight_sensitivity,
)

DEADLINE = datetime(2027, 3, 15, 17, 0, tzinfo=timezone.utc)


def sample_plan(country: str | None = "NGA"):
    documents = [
        RequiredDocument(doc_type="passport"),
        RequiredDocument(doc_type="transcript"),
        RequiredDocument(doc_type="lor"),
        RequiredDocument(doc_type="nysc"),
        RequiredDocument(doc_type="sop"),
        RequiredDocument(doc_type="cv", mandatory=False),
    ]
    return generate_plan(
        cycle_id="cycle-1",
        cycle_deadline=DEADLINE,
        documents=documents,
        scholarship_id="sch-1",
        country_iso3=country,
    )


def test_plan_is_built_backwards_from_the_deadline() -> None:
    plan = sample_plan()
    assert plan.internal_deadline == DEADLINE - timedelta(days=7)
    assert plan.tasks

    passport = next(task for task in plan.tasks if task.doc_type == "passport")
    assert passport.due_at == plan.internal_deadline - timedelta(days=21)


def test_third_party_documents_are_scheduled_earlier() -> None:
    plan = sample_plan()
    transcript = next(task for task in plan.tasks if task.doc_type == "transcript")
    cv = next(task for task in plan.tasks if task.doc_type == "cv")
    assert transcript.due_at < cv.due_at
    assert transcript.task_type == "request"


def test_country_adjustments_extend_lead_times() -> None:
    base = lead_time_for("nysc")
    nigerian = lead_time_for("nysc", country_iso3="NGA")
    assert nigerian.days > base.days
    assert nigerian.country_adjusted


def test_plan_without_a_deadline_warns_instead_of_inventing_dates() -> None:
    plan = generate_plan(cycle_id="c", cycle_deadline=None, documents=[RequiredDocument(doc_type="passport")])
    assert plan.warnings
    assert all(task.due_at is None for task in plan.tasks)


def test_plan_warns_about_third_party_dependencies() -> None:
    plan = sample_plan()
    assert any("third party" in warning for warning in plan.warnings)


def test_tasks_can_be_sorted_with_undated_last() -> None:
    plan = sample_plan()
    ordered = sort_tasks(plan.tasks)
    dated = [task for task in ordered if task.due_at is not None]
    undated = [task for task in ordered if task.due_at is None]
    assert dated and not undated or not dated
    assert ordered[: len(dated)] == dated


def test_ics_export_contains_events_and_the_deadline() -> None:
    plan = sample_plan()
    ics = plan_to_ics(plan)
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in ics
    assert "Official application deadline" in ics
    assert ics.rstrip().endswith("END:VCALENDAR")


def test_markdown_export_is_a_checklist() -> None:
    plan = sample_plan()
    markdown = plan_to_markdown(plan, scholarship_name="Chevening 2027")
    assert "# Chevening 2027" in markdown
    assert "- [ ]" in markdown
    assert "planning estimates" in markdown


def test_csv_export_of_a_shortlist() -> None:
    csv_text = shortlist_to_csv([{"name": "A", "deadline": "2027-03-15"}, {"name": "B"}])
    assert "name,deadline" in csv_text
    assert "A,2027-03-15" in csv_text


def test_weights_are_normalised() -> None:
    weights = normalise_weights({"confirmed_eligibility": 1.0, "deadline_urgency": 1.0})
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_ranking_is_transparent_and_labelled() -> None:
    opportunity = score_opportunity(
        scholarship_id="s1",
        name="Chevening",
        factors={"confirmed_eligibility": 1.0, "deadline_urgency": 0.5},
        reasons=["You meet the nationality requirement"],
    )
    payload = opportunity.to_dict()
    assert payload["factors"]
    assert "not a probability" in payload["interpretation"]
    assert payload["weighted_factors"]


def test_ranking_orders_by_score() -> None:
    a = score_opportunity(scholarship_id="a", name="A", factors={"confirmed_eligibility": 1.0})
    b = score_opportunity(scholarship_id="b", name="B", factors={"confirmed_eligibility": 0.1})
    ranked = rank_opportunities([b, a])
    assert ranked[0].scholarship_id == "a"


def test_weight_sensitivity_reports_stability() -> None:
    opportunities = [
        score_opportunity(scholarship_id="a", name="A", factors={"confirmed_eligibility": 0.9, "deadline_urgency": 0.1}),
        score_opportunity(scholarship_id="b", name="B", factors={"confirmed_eligibility": 0.5, "deadline_urgency": 0.9}),
        score_opportunity(scholarship_id="c", name="C", factors={"confirmed_eligibility": 0.2, "deadline_urgency": 0.4}),
    ]
    sensitivity = weight_sensitivity(opportunities)
    assert sensitivity["variants_tested"] == len(DEFAULT_WEIGHTS) * 2
    assert -1.0 <= sensitivity["mean_kendall_tau"] <= 1.0
    assert 0.0 <= sensitivity["mean_top10_churn"] <= 1.0


def test_weight_descriptions_are_slider_ready() -> None:
    described = describe_weights()
    assert len(described) == len(DEFAULT_WEIGHTS)
    assert all("label" in item and "weight" in item for item in described)
