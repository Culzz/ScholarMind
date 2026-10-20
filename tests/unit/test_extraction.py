"""Tests for rule-based extraction and its validation gates."""

from __future__ import annotations

from scholarmind.extraction.extract import extract_all, extract_deadlines, extract_documents, extract_eligibility
from scholarmind.extraction.schema import ClaimType, FactStatus
from scholarmind.extraction.validate import apply_confidence_policy, validate_result, validate_spans

PAGE = """
Chevening Scholarships Programme 2027

The Chevening programme is open to citizens of Nigeria, Ghana, Kenya and other eligible countries.
Applicants must hold a bachelor's degree from a recognised institution and must be aged between 18 and 35 years.

The programme covers full tuition fees, a monthly stipend, travel costs and accommodation.
Financial support is subject to the availability of funds.

You must submit the following documents:
- A valid passport
- Academic transcript
- Statement of purpose
- Two letters of reference
- IELTS certificate with a score of 6.5 or above
- NYSC certificate

Applications open on 4 August 2026. The application deadline is 12 November 2026 at 17:00 GMT.
"""


def test_deadline_is_extracted_with_a_span() -> None:
    facts = extract_deadlines(PAGE)
    deadlines = [f for f in facts if f.claim_type is ClaimType.DEADLINE]
    assert deadlines
    fact = deadlines[0]
    assert fact.span_start >= 0
    assert PAGE[fact.span_start : fact.span_end].strip().startswith("The application deadline")
    assert fact.normalized_value["precision"] == "exact"


def test_opening_date_is_distinguished_from_the_deadline() -> None:
    facts = extract_deadlines(PAGE)
    kinds = {fact.claim_type for fact in facts}
    assert ClaimType.OPENING_DATE in kinds
    assert ClaimType.DEADLINE in kinds


def test_unparseable_deadline_is_unresolved_not_guessed() -> None:
    facts = extract_deadlines("The application deadline is soon.")
    assert facts
    assert facts[0].normalized_value is None
    assert facts[0].status is FactStatus.UNRESOLVED


def test_funding_components_are_extracted_separately() -> None:
    result = extract_all(PAGE)
    components = {item.component: item.coverage for item in result.funding}
    assert "tuition" in components
    assert "stipend" in components
    assert "travel" in components
    assert "accommodation" in components


def test_required_documents_are_extracted() -> None:
    documents = extract_documents(PAGE)
    types = {doc.doc_type for doc in documents}
    assert "passport" in types
    assert "transcript" in types
    assert "sop" in types
    assert "nysc" in types


def test_eligibility_rules_are_typed() -> None:
    rules = extract_eligibility(PAGE)
    kinds = {rule.kind for rule in rules}
    assert "nationality" in kinds
    assert "age" in kinds
    assert "degree_level" in kinds
    assert "language" in kinds

    nationality = next(rule for rule in rules if rule.kind == "nationality")
    assert "NGA" in nationality.value

    age = next(rule for rule in rules if rule.kind == "age" and rule.subject == "age.max")
    assert age.value == [18, 35]


def test_spans_are_validated_against_the_source() -> None:
    result = extract_all(PAGE)
    report = validate_spans(result, PAGE)
    assert report.ok
    assert len(report.accepted) == len(result.facts)


def test_out_of_range_spans_are_rejected() -> None:
    result = extract_all(PAGE)
    result.facts[0].span_start = 10_000
    report = validate_spans(result, PAGE)
    assert not report.ok
    assert report.rejected


def test_confidence_policy_splits_buckets() -> None:
    result = extract_all(PAGE)
    result.facts.append(
        type(result.facts[0])(
            claim_type=ClaimType.GENERAL,
            text="x",
            span_start=0,
            span_end=1,
            confidence=0.95,
        )
    )
    buckets = apply_confidence_policy(result.facts)
    assert buckets["confirmed"]
    assert buckets["confirmed"][0].status is FactStatus.CONFIRMED


def test_validation_produces_a_publishable_result() -> None:
    result = extract_all(PAGE)
    report, validated = validate_result(result, PAGE)
    assert report.ok
    assert validated.facts
    assert all(fact.confidence >= 0.7 for fact in validated.facts)
    assert validated.eligibility
