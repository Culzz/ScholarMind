"""Answer generation contracts and citation validation.

Generation is constrained so that the model can only *report* what the retrieved
evidence contains. Three gates are applied to every answer before it reaches a user:

1. **Referential** - every cited evidence id must exist in the retrieved context.
2. **Support**     - the referenced chunk must actually contain the claim's key
                    entities and numbers. Merely having a URL is not support.
3. **Reconciliation** - dates and amounts quoted in prose are compared against the
                    structured records; a mismatch downgrades the claim to
                    ``needs_verification``.

If no claim survives the gates, the answer is replaced by an abstention that states
what is missing and what the student can do next.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

CONFIDENCE_STATES = ("confirmed", "uncertain", "needs_verification")

_NUMERIC_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
_DATE_TOKEN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\b")
_KEY_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


@dataclass
class Claim:
    """A single factual statement made by the assistant."""

    text: str
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "confirmed"
    fact_ref: dict[str, Any] | None = None
    validation_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": self.evidence_ids,
            "status": self.status,
            "fact_ref": self.fact_ref,
            "validation_notes": self.validation_notes,
        }


@dataclass
class ValidatedAnswer:
    """The result of validating a generated answer."""

    claims: list[Claim]
    abstained: bool
    abstention_reason: str | None = None
    missing_information: list[str] = field(default_factory=list)
    freshness_warnings: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    dropped_claim_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [c.to_dict() for c in self.claims],
            "abstained": self.abstained,
            "abstention_reason": self.abstention_reason,
            "missing_information": self.missing_information,
            "freshness_warnings": self.freshness_warnings,
            "conflicts": self.conflicts,
            "dropped_claim_count": self.dropped_claim_count,
        }


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _KEY_TOKEN.findall(text)}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMERIC_TOKEN.findall(text)}


def has_support(claim_text: str, chunk_text: str, *, min_token_overlap: float = 0.6) -> bool:
    """Heuristic support check between a claim and a cited chunk.

    The claim is considered supported when a sufficient share of its significant
    tokens, and all of its numbers and dates, appear in the chunk. This is a cheap,
    explainable proxy for entailment; the evaluation harness measures how well it
    correlates with human judgement and the threshold is tuned on the dev split.
    """
    claim_tokens = _tokens(claim_text)
    if not claim_tokens:
        return False
    chunk_tokens = _tokens(chunk_text)
    overlap = len(claim_tokens & chunk_tokens) / len(claim_tokens)
    if overlap < min_token_overlap:
        return False
    claim_numbers = _numbers(claim_text)
    chunk_numbers = _numbers(chunk_text)
    if claim_numbers and not claim_numbers.issubset(chunk_numbers):
        return False
    claim_dates = {d.lower() for d in _DATE_TOKEN.findall(claim_text)}
    chunk_dates = {d.lower() for d in _DATE_TOKEN.findall(chunk_text)}
    if claim_dates and not claim_dates.issubset(chunk_dates):
        return False
    return True


def reconcile_value(claim_text: str, structured_value: Any) -> bool:
    """Check that a quoted date/amount agrees with the structured record."""
    if structured_value is None:
        return True
    if isinstance(structured_value, (date, datetime)):
        target = structured_value.strftime("%Y-%m-%d")
        return target in claim_text or structured_value.strftime("%d %B %Y") in claim_text
    if isinstance(structured_value, (int, float)):
        return str(structured_value) in claim_text.replace(",", "")
    return True


def validate_answer(
    *,
    claims: Sequence[Mapping[str, Any]],
    retrieved_chunks: Mapping[str, str],
    structured_facts: Mapping[str, Any] | None = None,
) -> ValidatedAnswer:
    """Run the three validation gates over a generated answer.

    Parameters
    ----------
    claims:
        The model's structured claims (``text``, ``evidence_ids``, optional ``fact_ref``).
    retrieved_chunks:
        Mapping of chunk id -> chunk text for the chunks actually placed in context.
    structured_facts:
        Optional mapping of ``"<entity>.<field>"`` -> structured value used for
        reconciliation of dates and amounts.
    """
    structured_facts = structured_facts or {}
    validated: list[Claim] = []
    dropped = 0

    for raw in claims:
        claim = Claim(
            text=str(raw.get("text", "")).strip(),
            evidence_ids=[str(i) for i in (raw.get("evidence_ids") or [])],
            status=str(raw.get("status") or "confirmed"),
            fact_ref=raw.get("fact_ref"),
        )
        if not claim.text:
            dropped += 1
            continue

        kept: list[str] = []
        for evidence_id in claim.evidence_ids:
            chunk = retrieved_chunks.get(evidence_id)
            if chunk is None:
                claim.validation_notes.append(f"evidence {evidence_id} was not in the retrieved context")
                continue
            if not has_support(claim.text, chunk):
                claim.validation_notes.append(f"evidence {evidence_id} does not appear to support the claim")
                continue
            kept.append(evidence_id)

        if not kept:
            dropped += 1
            continue

        claim.evidence_ids = kept
        if claim.status == "confirmed" and len(kept) < len(claim.evidence_ids):
            claim.status = "uncertain"

        fact_ref = claim.fact_ref or {}
        key = fact_ref.get("field")
        entity = fact_ref.get("entity")
        if entity and key:
            structured_value = structured_facts.get(f"{entity}.{key}")
            if structured_value is not None and not reconcile_value(claim.text, structured_value):
                claim.status = "needs_verification"
                claim.validation_notes.append("quoted value differs from the structured record")

        validated.append(claim)

    if not validated:
        return ValidatedAnswer(
            claims=[],
            abstained=True,
            abstention_reason=(
                "The official material I could reach does not establish an answer to "
                "this question."
            ),
            dropped_claim_count=dropped,
        )

    return ValidatedAnswer(claims=validated, abstained=False, dropped_claim_count=dropped)


def build_abstention(missing_information: Iterable[str], conflicts: Sequence[Mapping[str, Any]] | None = None) -> ValidatedAnswer:
    """Construct an explicit abstention with actionable next steps."""
    missing = list(missing_information)
    conflict_list = [dict(c) for c in (conflicts or [])]
    if conflict_list:
        reason = "Official sources disagree on this point, so I will not assert a single value."
    else:
        reason = "The official material reviewed does not establish this yet."
    return ValidatedAnswer(
        claims=[],
        abstained=True,
        abstention_reason=reason,
        missing_information=missing,
        conflicts=conflict_list,
    )
