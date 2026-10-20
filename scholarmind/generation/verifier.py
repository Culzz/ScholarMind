"""Claim-level verifier.

Every generated claim is checked against the evidence it cites. The verifier
answers one question: *does this excerpt actually support this statement?*

Two verifier implementations are provided:

* :class:`LexicalEntailmentVerifier` - deterministic, dependency-free, and
  always available. It checks token overlap and that every number and date in
  the claim appears in the excerpt.
* :class:`JudgeEntailmentVerifier` - delegates to a judge model. It is only
  trusted once it has been validated against human labels
  (``docs/EVALUATION.md`` §15); until then it runs alongside the lexical
  verifier rather than replacing it.

A claim that fails verification is removed from the answer or marked
``unverified``. It is never presented as a supported fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from scholarmind.generation.validation import Claim, has_support

_KEY_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were", "has",
    "have", "will", "their", "they", "them", "its", "you", "your", "our", "not", "but",
    "all", "any", "can", "may", "must", "should", "would", "there", "which", "when",
    "where", "what", "who", "how", "been", "being", "than", "then", "into", "also",
}


@dataclass
class VerificationOutcome:
    """The verdict for one claim against one excerpt."""

    supported: bool
    score: float
    reason: str
    verifier: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "score": self.score,
            "reason": self.reason,
            "verifier": self.verifier,
        }


class EntailmentVerifier(Protocol):
    """A verifier that judges whether an excerpt supports a claim."""

    name: str

    def verify(self, claim_text: str, excerpt: str) -> VerificationOutcome:
        ...


class LexicalEntailmentVerifier:
    """Deterministic support check.

    A claim is supported when a sufficient share of its significant words, and
    all of its numbers and dates, appear in the excerpt. The threshold is
    deliberately strict: an unsupported claim that reaches the user is a
    correctness failure, while a false rejection is merely a missed answer.
    """

    name = "lexical-entailment"

    def __init__(self, *, min_token_overlap: float = 0.6) -> None:
        self.min_token_overlap = min_token_overlap

    def verify(self, claim_text: str, excerpt: str) -> VerificationOutcome:
        claim_tokens = {t.lower() for t in _KEY_TOKEN.findall(claim_text)} - _STOPWORDS
        if not claim_tokens:
            return VerificationOutcome(False, 0.0, "claim contains no checkable terms", self.name)

        excerpt_tokens = {t.lower() for t in _KEY_TOKEN.findall(excerpt)}
        overlap = len(claim_tokens & excerpt_tokens) / len(claim_tokens)

        claim_numbers = {n.replace(",", "") for n in _NUMBER.findall(claim_text)}
        excerpt_numbers = {n.replace(",", "") for n in _NUMBER.findall(excerpt)}
        missing_numbers = claim_numbers - excerpt_numbers

        if missing_numbers:
            return VerificationOutcome(
                False,
                overlap,
                f"numbers {sorted(missing_numbers)} do not appear in the cited excerpt",
                self.name,
            )

        if overlap < self.min_token_overlap:
            return VerificationOutcome(
                False,
                overlap,
                f"only {overlap:.0%} of the claim's terms appear in the cited excerpt",
                self.name,
            )

        return VerificationOutcome(
            True,
            overlap,
            f"{overlap:.0%} of the claim's terms appear in the cited excerpt",
            self.name,
        )


class JudgeEntailmentVerifier:
    """Delegates the judgement to a judge callable.

    ``judge`` receives ``(claim_text, excerpt)`` and returns a boolean. The
    caller is responsible for ensuring the judge has been calibrated against
    human labels before it is trusted as the primary verifier.
    """

    name = "judge-entailment"

    def __init__(self, judge: Callable[[str, str], bool]) -> None:
        self._judge = judge

    def verify(self, claim_text: str, excerpt: str) -> VerificationOutcome:
        try:
            supported = bool(self._judge(claim_text, excerpt))
        except Exception as exc:  # a failing judge must not fail the answer
            return VerificationOutcome(False, 0.0, f"judge error: {type(exc).__name__}", self.name)
        return VerificationOutcome(
            supported,
            1.0 if supported else 0.0,
            "judge accepted the claim" if supported else "judge rejected the claim",
            self.name,
        )


@dataclass
class VerifiedClaim:
    """A claim with its verification outcome attached."""

    claim: Claim
    supported: bool
    score: float
    reason: str
    verifier: str
    unverified_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = self.claim.to_dict()
        payload["verification"] = {
            "supported": self.supported,
            "score": self.score,
            "reason": self.reason,
            "verifier": self.verifier,
        }
        if self.unverified_reason:
            payload["unverified_reason"] = self.unverified_reason
        return payload


@dataclass
class VerificationReport:
    """The result of verifying every claim of an answer."""

    claims: list[VerifiedClaim] = field(default_factory=list)
    dropped: int = 0

    @property
    def supported_claims(self) -> list[VerifiedClaim]:
        return [claim for claim in self.claims if claim.supported]

    @property
    def unsupported_claims(self) -> list[VerifiedClaim]:
        return [claim for claim in self.claims if not claim.supported]

    @property
    def citation_precision(self) -> float:
        """Share of claims that passed verification."""
        if not self.claims:
            return 0.0
        return len(self.supported_claims) / len(self.claims)

    def summary(self) -> dict[str, Any]:
        return {
            "claims": len(self.claims),
            "supported": len(self.supported_claims),
            "unsupported": len(self.unsupported_claims),
            "dropped": self.dropped,
            "citation_precision": self.citation_precision,
        }


class ClaimVerifier:
    """Runs verifiers over the claims of a generated answer.

    Parameters
    ----------
    verifier:
        The primary verifier.
    secondary:
        An optional second verifier. When both run, a claim is supported only if
        the primary verifier accepts it and the secondary does not reject it.
    """

    def __init__(
        self,
        verifier: EntailmentVerifier | None = None,
        *,
        secondary: EntailmentVerifier | None = None,
        require_all_evidence: bool = True,
    ) -> None:
        self.verifier = verifier or LexicalEntailmentVerifier()
        self.secondary = secondary
        self.require_all_evidence = require_all_evidence

    def verify_claim(self, claim: Claim, excerpts: dict[str, str]) -> VerifiedClaim:
        """Verify one claim against the excerpts it cites."""
        if not claim.evidence_ids:
            return VerifiedClaim(claim, False, 0.0, "claim cites no evidence", self.verifier.name)

        outcomes: list[VerificationOutcome] = []
        for evidence_id in claim.evidence_ids:
            excerpt = excerpts.get(evidence_id)
            if excerpt is None:
                outcomes.append(
                    VerificationOutcome(False, 0.0, f"evidence {evidence_id} was not retrieved", self.verifier.name)
                )
                continue
            outcomes.append(self.verifier.verify(claim.text, excerpt))

        supported = all(outcome.supported for outcome in outcomes) if self.require_all_evidence else any(
            outcome.supported for outcome in outcomes
        )

        if supported and self.secondary is not None:
            for evidence_id, outcome in zip(claim.evidence_ids, outcomes):
                excerpt = excerpts.get(evidence_id)
                if excerpt is None:
                    continue
                secondary = self.secondary.verify(claim.text, excerpt)
                if not secondary.supported:
                    supported = False
                    outcomes[claim.evidence_ids.index(evidence_id)] = secondary
                    break

        reason = "; ".join(outcome.reason for outcome in outcomes)
        score = min((outcome.score for outcome in outcomes), default=0.0)
        return VerifiedClaim(claim, supported, score, reason, self.verifier.name)

    def verify(self, claims: Sequence[Claim], excerpts: dict[str, str]) -> VerificationReport:
        """Verify every claim of an answer."""
        report = VerificationReport()
        for claim in claims:
            verified = self.verify_claim(claim, excerpts)
            report.claims.append(verified)
            if not verified.supported:
                report.dropped += 1
        return report


def support_by_has_support(claim_text: str, excerpt: str) -> bool:
    """Convenience wrapper around the shared lexical support check."""
    return has_support(claim_text, excerpt)
