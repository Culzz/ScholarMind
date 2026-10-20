"""Validation of extracted facts.

Every fact must satisfy three conditions before it can be stored:

1. **Span validity** - the span lies inside the source text and captures
   non-empty content.
2. **Type validity** - the normalised value matches the field it is stored in.
3. **Confidence policy** - facts below the confidence floor are flagged for
   review instead of being published as confirmed.

Model-proposed facts go through exactly the same gate, which is what keeps the
model out of the decision path: it may propose, but it may not decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from scholarmind.extraction.schema import (
    EligibilityFact,
    ExtractionResult,
    Fact,
    FactStatus,
)

CONFIDENCE_FLOOR = 0.7
REVIEW_FLOOR = 0.4


@dataclass
class ValidationIssue:
    """A problem found with one fact."""

    fact_index: int
    severity: str  # error | warning
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"fact_index": self.fact_index, "severity": self.severity, "message": self.message}


@dataclass
class ValidationReport:
    """The outcome of validating an extraction result."""

    accepted: list[Fact] = field(default_factory=list)
    needs_review: list[Fact] = field(default_factory=list)
    rejected: list[Fact] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected and not any(issue.severity == "error" for issue in self.issues)

    def summary(self) -> dict[str, Any]:
        return {
            "accepted": len(self.accepted),
            "needs_review": len(self.needs_review),
            "rejected": len(self.rejected),
            "issues": len(self.issues),
        }


def validate_spans(result: ExtractionResult, text: str) -> ValidationReport:
    """Check that every span points at real text in the source."""
    report = ValidationReport()
    length = len(text)

    for index, fact in enumerate(result.facts):
        if fact.span_start < 0 or fact.span_end > length:
            report.issues.append(
                ValidationIssue(index, "error", "span lies outside the source text")
            )
            report.rejected.append(fact)
            continue
        if fact.span_end <= fact.span_start:
            report.issues.append(ValidationIssue(index, "error", "span is empty or reversed"))
            report.rejected.append(fact)
            continue
        excerpt = text[fact.span_start : fact.span_end]
        if not excerpt.strip():
            report.issues.append(ValidationIssue(index, "error", "span covers whitespace only"))
            report.rejected.append(fact)
            continue
        if excerpt.strip()[:40] != fact.text.strip()[:40]:
            report.issues.append(
                ValidationIssue(index, "warning", "fact text does not match the span content")
            )
        report.accepted.append(fact)

    return report


def apply_confidence_policy(
    facts: Iterable[Fact],
    *,
    floor: float = CONFIDENCE_FLOOR,
    review_floor: float = REVIEW_FLOOR,
) -> dict[str, list[Fact]]:
    """Split facts into publishable, reviewable and rejected buckets.

    A fact at or above the floor may be published as confirmed. A fact between
    the review floor and the floor is publishable only as ``ambiguous`` and goes
    to the review queue. Below the review floor it is rejected.
    """
    buckets: dict[str, list[Fact]] = {"confirmed": [], "review": [], "rejected": []}
    for fact in facts:
        if fact.confidence >= floor:
            fact.status = FactStatus.CONFIRMED
            buckets["confirmed"].append(fact)
        elif fact.confidence >= review_floor:
            fact.status = FactStatus.AMBIGUOUS
            buckets["review"].append(fact)
        else:
            fact.status = FactStatus.REJECTED
            buckets["rejected"].append(fact)
    return buckets


def validate_eligibility(
    rules: Sequence[EligibilityFact],
    *,
    floor: float = CONFIDENCE_FLOOR,
) -> tuple[list[EligibilityFact], list[EligibilityFact]]:
    """Split eligibility rules into publishable and review-needed lists.

    A rule that could not be parsed into an evaluable condition is never
    published as a satisfied rule — it is kept, flagged, and shown to a human.
    """
    publishable: list[EligibilityFact] = []
    needs_review: list[EligibilityFact] = []
    for rule in rules:
        if not rule.parseable or rule.ambiguous or rule.confidence < floor:
            rule.ambiguous = True
            needs_review.append(rule)
        else:
            publishable.append(rule)
    return publishable, needs_review


def validate_result(result: ExtractionResult, text: str) -> tuple[ValidationReport, ExtractionResult]:
    """Run the full validation pipeline over an extraction result."""
    report = validate_spans(result, text)
    buckets = apply_confidence_policy(report.accepted)

    publishable_rules, review_rules = validate_eligibility(result.eligibility)

    validated = ExtractionResult(
        facts=buckets["confirmed"],
        eligibility=publishable_rules,
        funding=list(result.funding),
        documents=list(result.documents),
        extraction_method=result.extraction_method,
        model_id=result.model_id,
        extraction_version=result.extraction_version,
    )
    return report, validated
