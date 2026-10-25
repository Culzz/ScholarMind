"""Deadline selection must not promote a different event's date.

Chevening publishes an "Offer deadline" after the application window closes.
Taking the first date on the page (or the only remaining one) turned that into
the application deadline.
"""

from __future__ import annotations

from scholarmind.extraction.schema import ClaimType, Fact, FactStatus
from scholarmind.normalization.cycles import _deadline_score, _select_deadline, build_cycles


def _deadline(text: str, value: str) -> Fact:
    return Fact(
        claim_type=ClaimType.DEADLINE,
        text=text,
        span_start=0,
        span_end=max(1, len(text)),
        normalized_value={"value": value, "precision": "exact", "raw_text": text},
        field_name="deadline_at",
        confidence=0.85,
        status=FactStatus.CONFIRMED,
    )


def test_offer_deadline_is_not_an_application_deadline() -> None:
    fact = _deadline("8 July 2027 - Offer deadline", "2027-07-08")

    assert _deadline_score(fact) < 0
    assert _select_deadline([fact]) is None


def test_application_deadline_wins_over_an_offer_date() -> None:
    application = _deadline("Applications close on 12 November 2026", "2026-11-12")
    offer = _deadline("8 July 2027 - Offer deadline", "2027-07-08")

    assert _select_deadline([offer, application]) is application


def test_a_cycle_keeps_an_unknown_deadline_rather_than_guessing() -> None:
    cycles = build_cycles(
        [_deadline("8 July 2027 - Offer deadline", "2027-07-08")],
        text="Chevening 2027",
        default_intake_year=2027,
    )

    assert cycles[0].deadline_at is None
    assert cycles[0].status == "undetermined"
    assert "stays unknown" in (cycles[0].notes or "")


def test_opening_dates_are_not_classified_as_deadlines() -> None:
    from scholarmind.extraction.extract import extract_deadlines

    for line in (
        "21 October 2026 - Opening date:",
        "1 April 2026 - Applications open for the 2027 admission cycle.",
    ):
        facts = extract_deadlines(line)
        assert facts, line
        assert all(fact.claim_type is ClaimType.OPENING_DATE for fact in facts), line

    facts = extract_deadlines("Applications close on 12 November 2026.")
    assert [fact.claim_type for fact in facts] == [ClaimType.DEADLINE]
