"""Tests for date parsing, cycle normalisation and vocabulary mapping."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from scholarmind.normalization.cycles import build_cycles, choose_current_cycles, detect_intake_years
from scholarmind.normalization.dates import cycle_status, days_until, deadline_is_open, parse_date, parse_datetime
from scholarmind.normalization.fields import (
    normalise_country,
    normalise_degree_level,
    normalise_document_type,
    normalise_funding_component,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Applications close on 12 March 2027.", date(2027, 3, 12)),
        ("Closing date: 12th March 2027", date(2027, 3, 12)),
        ("Deadline: March 12, 2027", date(2027, 3, 12)),
        ("Deadline: 2027-03-12", date(2027, 3, 12)),
        ("Deadline: 15/06/2027", date(2027, 6, 15)),
    ],
)
def test_exact_dates_are_parsed(text: str, expected: date) -> None:
    parsed = parse_date(text)
    assert parsed.value == expected
    assert parsed.precision == "exact"


def test_month_precision_is_preserved() -> None:
    parsed = parse_date("Applications close in March 2027.")
    assert parsed.value == date(2027, 3, 1)
    assert parsed.precision == "month"


def test_year_precision_is_preserved() -> None:
    parsed = parse_date("Applications for 2027 open later.")
    assert parsed.precision == "year"
    assert parsed.value == date(2027, 1, 1)


def test_unparseable_date_is_unknown_not_a_guess() -> None:
    parsed = parse_date("Applications close soon.")
    assert parsed.value is None
    assert parsed.precision == "unknown"


def test_datetime_parsing_detects_clock_time() -> None:
    parsed = parse_datetime("Applications close 12 March 2027 at 17:00 GMT")
    assert parsed.is_datetime
    assert parsed.timezone == "GMT"


def test_deadline_is_open_handles_unknown() -> None:
    assert deadline_is_open(None) is None
    assert deadline_is_open(date(2027, 1, 1), now=NOW) is True
    assert deadline_is_open(date(2026, 1, 1), now=NOW) is False


def test_cycle_status_never_claims_open_without_a_deadline() -> None:
    assert cycle_status(None, None, now=NOW) == "undetermined"
    assert cycle_status(date(2027, 1, 1), None, now=NOW) == "open"
    assert cycle_status(date(2026, 1, 1), None, now=NOW) == "closed"
    assert cycle_status(None, date(2027, 6, 1), now=NOW) == "upcoming"


def test_days_until() -> None:
    assert days_until(date(2026, 10, 30), now=NOW) == 10
    assert days_until(None) is None


def test_country_normalisation() -> None:
    assert normalise_country("Nigeria") == "NGA"
    assert normalise_country("nigeria") == "NGA"
    assert normalise_country("United Kingdom") == "GBR"
    assert normalise_country("Atlantis") is None


def test_degree_level_normalisation() -> None:
    assert normalise_degree_level("PhD") == "phd"
    assert normalise_degree_level("Master's degree") == "masters"
    assert normalise_degree_level("postgraduate") == "masters"
    assert normalise_degree_level("wizardry") is None


def test_funding_component_normalisation() -> None:
    assert normalise_funding_component("tuition fees") == "tuition"
    assert normalise_funding_component("living allowance") == "stipend"
    assert normalise_funding_component("airfare") == "travel"
    assert normalise_funding_component("mystery") is None


def test_document_type_normalisation() -> None:
    assert normalise_document_type("Statement of Purpose") == "sop"
    assert normalise_document_type("Academic Transcript") == "transcript"
    assert normalise_document_type("National Youth Service Corps Certificate") == "nysc"
    assert normalise_document_type("a poem") is None


def test_intake_year_detection() -> None:
    assert detect_intake_years("Apply for the 2027 intake; sessions run from 2026 to 2027.") == [2026, 2027]


def test_build_cycles_from_extracted_facts() -> None:
    from scholarmind.extraction.extract import extract_all

    text = (
        "The Chevening 2027 Scholarships programme is open.\n"
        "Applications open on 4 August 2026 and the application deadline is 12 November 2026 at 17:00 GMT.\n"
    )
    result = extract_all(text)
    cycles = build_cycles(result.facts, text=text, default_intake_year=2027, now=NOW)

    current = choose_current_cycles(cycles)
    assert current
    cycle = current[0]
    assert cycle.intake_year == 2027
    assert cycle.status == "open"
    assert cycle.deadline_precision == "exact"
    assert cycle.deadline_raw_text
