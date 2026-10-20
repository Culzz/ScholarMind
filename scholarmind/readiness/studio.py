"""Readiness studio.

Maps a student's own evidence (what they wrote in their CV, what they uploaded,
what they told us) against a scholarship's selection criteria, and shows the
gaps.

The hard rule: **the system never fabricates achievements**. Every piece of
evidence it maps must originate from the student, and a criterion with no
student-supplied evidence is reported as a gap - never as met. The output is a
checklist of what to strengthen and which criterion to point the evidence at,
not a rewritten CV.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were", "has",
    "have", "will", "their", "they", "them", "its", "you", "your", "our", "not", "but",
    "all", "any", "can", "may", "must", "should", "would", "there", "which", "when",
    "where", "what", "who", "how", "been", "being", "than", "then", "into", "also",
    "about", "such", "other", "over", "and", "into", "the", "of", "in", "on", "to",
    "or", "as", "at", "by", "is", "be", "we", "it", "my",
}


@dataclass
class SelectionCriterion:
    """A criterion from the scholarship's selection criteria."""

    criterion_id: str
    text: str
    category: str = "academic"
    is_mandatory: bool = True
    weight: float = 1.0


@dataclass
class UserEvidence:
    """Evidence supplied by the student.

    ``is_user_supplied`` is always true for legitimate entries; the studio
    refuses to map anything that is not user-supplied.
    """

    evidence_id: str
    text: str
    source: str = "user_entry"
    is_user_supplied: bool = True


@dataclass
class CriterionMapping:
    """How well the student's evidence covers one criterion."""

    criterion: SelectionCriterion
    matched_evidence: list[str] = field(default_factory=list)
    coverage: float = 0.0
    status: str = "gap"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion.criterion_id,
            "criterion_text": self.criterion.text,
            "category": self.criterion.category,
            "mandatory": self.criterion.is_mandatory,
            "matched_evidence": list(self.matched_evidence),
            "coverage": round(self.coverage, 3),
            "status": self.status,
            "note": self.note,
        }


@dataclass
class ReadinessReport:
    """The full readiness picture for one scholarship."""

    scholarship_id: str
    mappings: list[CriterionMapping] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    unused_evidence: list[str] = field(default_factory=list)

    @property
    def readiness(self) -> float:
        """Share of criteria with evidence behind them (a checklist measure)."""
        if not self.mappings:
            return 0.0
        return sum(1 for mapping in self.mappings if mapping.status != "gap") / len(self.mappings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scholarship_id": self.scholarship_id,
            "readiness": round(self.readiness, 3),
            "readiness_interpretation": (
                "Share of selection criteria you already have evidence for. It is a "
                "checklist measure, not a selection prediction."
            ),
            "mappings": [mapping.to_dict() for mapping in self.mappings],
            "gaps": list(self.gaps),
            "suggestions": list(self.suggestions),
            "unused_evidence": list(self.unused_evidence),
            "no_fabrication_note": (
                "This report only uses evidence you supplied. Nothing here was written "
                "or completed for you, and no achievement was invented on your behalf."
            ),
        }


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text)} - _STOPWORDS


def _similarity(left: set[str], right: set[str]) -> float:
    """Overlap coefficient.

    The overlap coefficient is used rather than Jaccard because a short piece
    of evidence (a single CV bullet) can legitimately cover part of a longer
    criterion, and Jaccard would punish it for that.
    """
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def assess_readiness(
    *,
    scholarship_id: str,
    criteria: Sequence[SelectionCriterion],
    evidence: Sequence[UserEvidence],
    match_threshold: float = 0.12,
) -> ReadinessReport:
    """Map student evidence onto selection criteria and report the gaps."""
    report = ReadinessReport(scholarship_id=scholarship_id)
    usable = [item for item in evidence if item.is_user_supplied and item.text.strip()]

    used: set[str] = set()
    for criterion in criteria:
        criterion_tokens = _tokens(criterion.text)
        best_matches: list[tuple[float, str]] = []
        for item in usable:
            score = _similarity(criterion_tokens, _tokens(item.text))
            if score >= match_threshold:
                best_matches.append((score, item.evidence_id))

        best_matches.sort(reverse=True)
        matched = [evidence_id for _, evidence_id in best_matches]
        coverage = best_matches[0][0] if best_matches else 0.0
        used.update(matched)

        if not matched:
            status = "gap"
            note = "No evidence of yours covers this criterion yet."
            report.gaps.append(criterion.text)
            report.suggestions.append(
                f"Add a specific example that demonstrates: {criterion.text}"
            )
        elif coverage >= 0.35:
            status = "covered"
            note = "You have evidence that addresses this criterion."
        else:
            status = "partial"
            note = "Your evidence touches this criterion, but thinly."

        report.mappings.append(
            CriterionMapping(
                criterion=criterion,
                matched_evidence=matched,
                coverage=coverage,
                status=status,
                note=note,
            )
        )

    report.unused_evidence = [
        item.evidence_id for item in usable if item.evidence_id not in used
    ]
    return report
