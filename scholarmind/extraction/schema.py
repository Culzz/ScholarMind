"""Typed fact schema produced by extraction.

Every extracted fact carries the character span in the source text it came from.
A fact without a span cannot be stored: provenance is the whole point of the
platform, and a claim that cannot be pointed at is a claim nobody can verify.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class ClaimType(str, Enum):
    """What kind of fact a claim carries."""

    DEADLINE = "deadline"
    OPENING_DATE = "opening_date"
    FUNDING = "funding"
    ELIGIBILITY = "eligibility"
    DOCUMENT = "document"
    CONTACT = "contact"
    PROCESS = "process"
    GENERAL = "general"


class FactStatus(str, Enum):
    """Validation state of an extracted fact."""

    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    CONFLICTING = "conflicting"
    STALE = "stale"
    REJECTED = "rejected"


@dataclass
class Fact:
    """One extracted, span-anchored fact."""

    claim_type: ClaimType
    text: str
    span_start: int
    span_end: int
    normalized_value: Any = None
    field_name: str | None = None
    confidence: float = 0.0
    status: FactStatus = FactStatus.AMBIGUOUS
    extraction_method: str = "rule"
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.span_end <= self.span_start:
            raise ValueError("span_end must be greater than span_start")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_record(self) -> dict[str, Any]:
        """Serialisable representation for persistence."""
        return {
            "claim_type": self.claim_type.value,
            "text": self.text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "normalized_value": self.normalized_value,
            "field_name": self.field_name,
            "confidence": self.confidence,
            "status": self.status.value,
            "extraction_method": self.extraction_method,
            "notes": list(self.notes),
        }


@dataclass
class EligibilityFact:
    """An eligibility condition extracted from source text.

    The condition is expressed in terms the rule engine can evaluate. Anything
    that cannot be expressed that way is kept as prose with ``parseable=False``
    and is surfaced to a human rather than silently dropped.
    """

    kind: str
    subject: str
    operator: str
    value: Any
    rule_text: str
    span_start: int
    span_end: int
    mandatory: bool = True
    parseable: bool = True
    confidence: float = 0.0
    ambiguous: bool = False
    notes: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "operator": self.operator,
            "value": self.value,
            "rule_text": self.rule_text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "mandatory": self.mandatory,
            "parseable": self.parseable,
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
            "notes": list(self.notes),
        }


@dataclass
class FundingFact:
    """A funding component with its coverage status.

    ``coverage`` is one of included / excluded / conditional / unknown. A source
    that says "fully funded" does not automatically make every component
    ``included``; that is exactly the kind of silent assumption this schema
    exists to prevent.
    """

    component: str
    coverage: str
    amount: float | None = None
    currency: str | None = None
    amount_period: str | None = None
    conditions: str | None = None
    rule_text: str = ""
    span_start: int = 0
    span_end: int = 0
    confidence: float = 0.0

    def to_record(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "coverage": self.coverage,
            "amount": self.amount,
            "currency": self.currency,
            "amount_period": self.amount_period,
            "conditions": self.conditions,
            "rule_text": self.rule_text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "confidence": self.confidence,
        }


@dataclass
class DocumentFact:
    """A required document."""

    doc_type: str
    mandatory: bool = True
    description: str = ""
    lead_time_days: int | None = None
    requires_notarization: bool = False
    requires_apostille: bool = False
    requires_credential_evaluation: bool = False
    rule_text: str = ""
    span_start: int = 0
    span_end: int = 0
    confidence: float = 0.0

    def to_record(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "mandatory": self.mandatory,
            "description": self.description,
            "lead_time_days": self.lead_time_days,
            "requires_notarization": self.requires_notarization,
            "requires_apostille": self.requires_apostille,
            "requires_credential_evaluation": self.requires_credential_evaluation,
            "rule_text": self.rule_text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "confidence": self.confidence,
        }


@dataclass
class ExtractionResult:
    """Everything extracted from one snapshot."""

    facts: list[Fact] = field(default_factory=list)
    eligibility: list[EligibilityFact] = field(default_factory=list)
    funding: list[FundingFact] = field(default_factory=list)
    documents: list[DocumentFact] = field(default_factory=list)
    extraction_method: str = "rule"
    model_id: str | None = None
    extraction_version: str = "1"

    @property
    def low_confidence_count(self) -> int:
        return sum(1 for fact in self.facts if fact.confidence < 0.7)

    def summary(self) -> dict[str, Any]:
        return {
            "facts": len(self.facts),
            "eligibility_rules": len(self.eligibility),
            "funding_components": len(self.funding),
            "required_documents": len(self.documents),
            "low_confidence": self.low_confidence_count,
            "extraction_method": self.extraction_method,
            "model_id": self.model_id,
        }
