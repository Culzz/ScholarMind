"""Mechanical validation of LLM-drafted rule candidates.

The drafter may propose; only candidates whose quote exists in the source and
whose claimed values are literally inside that quote survive. These tests fix
that contract before any provider is attached.
"""

from __future__ import annotations

import pytest

from scholarmind.extraction.rule_drafter import (
    DraftCandidate,
    VALUE_NORMALISED_NOTE,
    build_draft_messages,
    draft_rules_for_text,
    parse_draft_response,
    validate_candidate,
    validate_rule_shape,
    validate_value_in_text,
)

SOURCE = (
    "Eligibility: applicants must hold a first degree of at least second class upper. "
    "Applicants must be citizens of Nigeria or Ghana, must not be over 35 years of age, "
    "and must have a minimum CGPA of 4.0 out of 5.0."
)

ACCEPTED_NATIONALITY = {
    "kind": "nationality",
    "subject": "nationality",
    "operator": "in",
    "value": ["Nigeria", "Ghana"],
    "mandatory": True,
    "rule_text": "Applicants must be citizens of Nigeria or Ghana",
}


class FakeProvider:
    """Returns canned output so the drafter is tested without any vendor SDK."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[str] = []

    def generate(self, request):  # noqa: ANN001 - protocol shape
        self.requests.append(request.messages[-1].content)
        from scholarmind.generation.provider import GenerationResponse

        return GenerationResponse(text=self.text, model=request.model)


def _nationality_candidate() -> DraftCandidate:
    span = SOURCE.find(ACCEPTED_NATIONALITY["rule_text"])
    return DraftCandidate(
        kind="nationality",
        subject="nationality",
        operator="in",
        value=["Nigeria", "Ghana"],
        rule_text=ACCEPTED_NATIONALITY["rule_text"],
        span_start=span,
        span_end=span + len(ACCEPTED_NATIONALITY["rule_text"]),
        confidence=0.8,
    )


def test_prompt_carries_the_hard_rules_and_schema() -> None:
    messages = build_draft_messages(SOURCE)
    system = messages[0].content
    assert "MUST be copied word for word" in system
    assert 'Output ONLY a JSON array' in system
    assert "nationality" in system and "second class" not in system  # no source words leak into the schema
    user = messages[1].content
    assert SOURCE in user


def test_valid_candidate_is_accepted_with_true_span() -> None:
    candidate = _nationality_candidate()
    assert validate_candidate(candidate, SOURCE) == []
    assert SOURCE[candidate.span_start : candidate.span_end] == candidate.rule_text


def test_candidate_whose_quote_is_missing_from_the_source_is_rejected() -> None:
    candidate = _nationality_candidate()
    candidate.span_start = 0
    candidate.span_end = 5
    errors = validate_candidate(candidate, SOURCE)
    assert any("span" in error for error in errors)


def test_candidate_whose_value_is_not_in_the_quote_is_rejected() -> None:
    candidate = _nationality_candidate()
    candidate.value = ["Nigeria", "Germany"]
    errors = validate_candidate(candidate, SOURCE)
    assert any("claimed value" in error for error in errors)


def test_unknown_kind_subject_or_operator_is_rejected() -> None:
    candidate = _nationality_candidate()
    errors = validate_rule_shape(kind="salary", subject="salary.min", operator="gte", value=1000, quote="1000")
    assert errors
    errors = validate_rule_shape(kind="nationality", subject="passport", operator="in", value=["Nigeria"])
    assert any("subject" in error for error in errors)
    errors = validate_rule_shape(kind="nationality", subject="nationality", operator="magic", value=1)
    assert any("operator" in error for error in errors)


def test_valueless_required_operator_passes_without_a_value() -> None:
    errors = validate_rule_shape(kind="nationality", subject="nationality", operator="required", value=None)
    assert errors == []


def test_value_matching_accepts_number_forms_in_ranges() -> None:
    quote = "must have a minimum CGPA of 4.0 out of 5.0"
    assert validate_value_in_text(4.0, quote)
    quote = "aged between 20 and 35 years"
    assert validate_value_in_text(35, quote)
    assert not validate_value_in_text(36, quote)


def test_parse_draft_response_computes_true_spans_and_filters_rejections() -> None:
    import json

    bogus = dict(ACCEPTED_NATIONALITY, rule_text="This sentence is not in the source")
    gpa_span = SOURCE.find("minimum CGPA of 4.0")
    payload = [
        ACCEPTED_NATIONALITY,
        bogus,
        {
            "kind": "gpa",
            "subject": "gpa.min_overall",
            "operator": "gte",
            "value": 4.0,
            "mandatory": True,
            "rule_text": SOURCE[gpa_span : gpa_span + 20],
        },
    ]
    outcome = parse_draft_response(json.dumps(payload), SOURCE)
    assert outcome.parse_error is None
    assert outcome.accepted_count == 2
    assert len(outcome.rejected) == 1


def test_parse_draft_response_reports_parse_failures_instead_of_guessing() -> None:
    outcome = parse_draft_response("I could not find eligibility rules here.", SOURCE)
    assert outcome.parse_error is not None
    assert outcome.candidates == []


def test_draft_rules_for_text_runs_end_to_end_with_a_fake_provider() -> None:
    import json

    response = json.dumps([ACCEPTED_NATIONALITY])
    outcome = draft_rules_for_text(FakeProvider(response), SOURCE, model="fake")
    assert outcome.accepted_count == 1
    candidate = outcome.candidates[0]
    assert candidate.kind == "nationality"
    assert SOURCE[candidate.span_start : candidate.span_end] == candidate.rule_text


def test_values_normalised_note_is_defined_for_the_reviewer() -> None:
    assert VALUE_NORMALISED_NOTE == "value_normalised_by_extractor"


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        ("Nigeria", "citizens of Nigeria or Ghana", True),
        ("nigeria", "citizens of Nigeria or Ghana", True),
        ("Nigeria", "citizens of Ghana", False),
        (["Nigeria", "Ghana"], "citizens of Nigeria or Ghana", True),
        (["Nigeria"], "citizens of Ghana", False),
        (None, "anything", True),
    ],
)
def test_value_containment_matrix(value, quote, expected) -> None:
    assert validate_value_in_text(value, quote) is expected
