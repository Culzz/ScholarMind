"""Eligibility reasoning engine.

The engine evaluates each rule of a scholarship cycle independently against a student
profile and returns one of four verdicts:

``satisfied``       The profile fact exists, is unambiguous, and meets the rule.
``not_satisfied``   The profile fact exists and demonstrably fails the rule.
``unknown``         The required profile fact is missing, so the question cannot be decided.
``needs_review``    Evidence conflicts between sources or the rule wording is ambiguous.

Two invariants define this module:

1. **A missing fact is never a satisfied rule.** No amount of downstream scoring may
   convert "unknown" into "satisfied".
2. **Every verdict carries a reason and its evidence.** A verdict without provenance
   is not produced.

The engine is deterministic: same profile + same rules -> same result. It never calls a
model; rule extraction happens in ``scholarmind.extraction`` and is validated before a
rule reaches this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class Verdict(str, Enum):
    """Outcome of evaluating a single eligibility rule."""

    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    UNKNOWN = "unknown"
    NEEDS_REVIEW = "needs_review"


class OverallStatus(str, Enum):
    """Aggregate status for a (profile, cycle) assessment."""

    ELIGIBLE = "eligible"
    LIKELY_ELIGIBLE = "likely_eligible"
    UNKNOWN = "unknown"
    NOT_ELIGIBLE = "not_eligible"
    NEEDS_REVIEW = "needs_review"


class Comparator(str, Enum):
    """Comparison operators supported by the rule engine."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GTE = "gte"
    LTE = "lte"
    BETWEEN = "between"
    CONTAINS = "contains"
    REQUIRED = "required"
    ABSENT = "absent"


class RuleComparability(str, Enum):
    """Whether failing a rule disqualifies the applicant."""

    MANDATORY = "mandatory"
    OPTIONAL = "optional"
    PREFERENCE = "preference"


@dataclass(frozen=True)
class Rule:
    """A typed, machine-checkable eligibility condition.

    Attributes
    ----------
    kind:
        What the rule constrains, e.g. ``nationality``, ``degree_level``, ``gpa``.
    subject:
        The profile field or facet the rule reads, e.g. ``gpa.min_overall``.
    comparator:
        How the fact is compared to ``value``.
    value:
        The threshold or condition, as a JSON-compatible structure.
    comparability:
        ``mandatory`` rules gate the overall status; optional rules do not.
    rule_text:
        Verbatim source wording. This is the anchor for the user-facing explanation.
    evidence_ids:
        Identifiers of the evidence claims that produced this rule.
    ambiguous:
        Set when the wording could not be interpreted confidently. Such a rule always
        yields ``needs_review`` rather than a confident verdict.
    """

    kind: str
    subject: str
    comparator: Comparator
    value: Any
    comparability: RuleComparability = RuleComparability.MANDATORY
    rule_text: str = ""
    evidence_ids: tuple[str, ...] = ()
    ambiguous: bool = False
    id: str | None = None


@dataclass(frozen=True)
class VerdictResult:
    """The outcome for a single rule, with its reasoning."""

    rule: Rule
    verdict: Verdict
    reason: str
    profile_fact: Any = None
    missing_field: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule.id,
            "kind": self.rule.kind,
            "subject": self.rule.subject,
            "comparability": self.rule.comparability.value,
            "rule_text": self.rule.rule_text,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "profile_fact": self.profile_fact,
            "missing_field": self.missing_field,
            "evidence_ids": list(self.evidence_ids or self.rule.evidence_ids),
        }


@dataclass
class Assessment:
    """Aggregate result of evaluating a profile against one cycle."""

    cycle_id: str
    engine_version: str
    results: list[VerdictResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        counts = {v.value: 0 for v in Verdict}
        for result in self.results:
            counts[result.verdict.value] += 1
        return counts

    @property
    def overall_status(self) -> OverallStatus:
        """Derive the overall label from per-rule verdicts.

        Precedence: a mandatory failure outranks everything; then ambiguity/conflict;
        then missing mandatory facts; only then a full pass.
        """
        mandatory = [r for r in self.results if r.rule.comparability is RuleComparability.MANDATORY]
        if any(r.verdict is Verdict.NOT_SATISFIED for r in mandatory):
            return OverallStatus.NOT_ELIGIBLE
        if any(r.verdict is Verdict.NEEDS_REVIEW for r in self.results):
            return OverallStatus.NEEDS_REVIEW
        if any(r.verdict is Verdict.UNKNOWN for r in mandatory):
            return OverallStatus.UNKNOWN
        if any(r.verdict is Verdict.UNKNOWN for r in self.results):
            return OverallStatus.LIKELY_ELIGIBLE
        return OverallStatus.ELIGIBLE

    @property
    def missing_fields(self) -> list[str]:
        """Profile fields that would resolve open ``unknown`` verdicts."""
        seen: list[str] = []
        for result in self.results:
            if result.verdict is Verdict.UNKNOWN and result.missing_field:
                if result.missing_field not in seen:
                    seen.append(result.missing_field)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "engine_version": self.engine_version,
            "overall_status": self.overall_status.value,
            "counts": self.counts,
            "missing_fields": self.missing_fields,
            "results": [r.to_dict() for r in self.results],
        }


# --- comparison helpers -------------------------------------------------

_NUMERIC = (int, float)


def _compare(left: Any, comparator: Comparator, right: Any) -> bool:
    """Apply a comparator to two facts. Unknown shapes raise, never guess."""
    if comparator is Comparator.EQUALS:
        return left == right
    if comparator is Comparator.NOT_EQUALS:
        return left != right
    if comparator is Comparator.IN:
        return left in right
    if comparator is Comparator.NOT_IN:
        return left not in right
    if comparator is Comparator.CONTAINS:
        return right in left
    if comparator is Comparator.REQUIRED:
        return bool(left) and left is not False
    if comparator is Comparator.ABSENT:
        return not left
    if comparator in (Comparator.GTE, Comparator.LTE, Comparator.BETWEEN):
        if comparator is Comparator.BETWEEN:
            if not isinstance(left, _NUMERIC) or not isinstance(right, (list, tuple)) or len(right) != 2:
                raise TypeError("between comparison requires a number and a two-element range")
            low, high = right
            return low <= left <= high
        if not isinstance(left, _NUMERIC) or not isinstance(right, _NUMERIC):
            raise TypeError(f"numeric comparison requires numbers, got {type(left)!r}/{type(right)!r}")
        if comparator is Comparator.GTE:
            return left >= right
        return left <= right
    raise ValueError(f"unsupported comparator: {comparator}")


class EligibilityEngine:
    """Evaluates a profile against the rules of a cycle.

    Parameters
    ----------
    version:
        Engine version string, recorded on every assessment for reproducibility.
    """

    version = "eligibility/1.0.0"

    def __init__(self, version: str | None = None) -> None:
        self.version = version or self.version

    # -- public API -------------------------------------------------------

    def evaluate(self, *, cycle_id: str, rules: Sequence[Rule], profile: Mapping[str, Any]) -> Assessment:
        """Evaluate every rule against ``profile``.

        ``profile`` is a flat mapping of profile field -> fact value. A key that is
        absent, or present with a ``None`` value, means the student has not supplied
        that fact, and any rule reading it yields ``unknown``.
        """
        assessment = Assessment(cycle_id=cycle_id, engine_version=self.version)
        for rule in rules:
            assessment.results.append(self._evaluate_rule(rule, profile))
        return assessment

    # -- internals --------------------------------------------------------

    def _evaluate_rule(self, rule: Rule, profile: Mapping[str, Any]) -> VerdictResult:
        if rule.ambiguous:
            return VerdictResult(
                rule=rule,
                verdict=Verdict.NEEDS_REVIEW,
                reason=(
                    "The official wording for this requirement is ambiguous, so the "
                    "requirement could not be applied automatically."
                ),
            )

        fact = self._resolve_fact(rule, profile)
        if fact is _MISSING:
            return VerdictResult(
                rule=rule,
                verdict=Verdict.UNKNOWN,
                reason=(
                    f"Your profile does not include '{rule.subject}', so this requirement "
                    "cannot be checked yet."
                ),
                missing_field=rule.subject,
            )

        try:
            passed = _compare(fact, rule.comparator, rule.value)
        except (TypeError, ValueError) as exc:
            return VerdictResult(
                rule=rule,
                verdict=Verdict.NEEDS_REVIEW,
                reason=f"This requirement could not be compared automatically ({exc}).",
                profile_fact=fact,
            )

        if passed:
            return VerdictResult(
                rule=rule,
                verdict=Verdict.SATISFIED,
                reason=f"Your profile value for '{rule.subject}' meets this requirement.",
                profile_fact=fact,
            )
        return VerdictResult(
            rule=rule,
            verdict=Verdict.NOT_SATISFIED,
            reason=f"Your profile value for '{rule.subject}' does not meet this requirement.",
            profile_fact=fact,
        )

    @staticmethod
    def _resolve_fact(rule: Rule, profile: Mapping[str, Any]) -> Any:
        """Read the profile fact a rule depends on.

        Rules may read either an exact field (``gpa.min_overall`` falls back to
        ``gpa``) or a list of fields (``nationality``/``residency``). Returning
        ``_MISSING`` keeps the unknown case explicit.
        """
        candidates: list[str] = []
        if "." in rule.subject:
            head, tail = rule.subject.split(".", 1)
            candidates.extend([rule.subject, head, tail])
        else:
            candidates.append(rule.subject)
            if rule.kind == "nationality":
                candidates.extend(["nationality", "residency", "citizenship"])
            elif rule.kind == "residency":
                candidates.extend(["residency", "nationality"])
            elif rule.kind == "degree_level":
                candidates.extend(["degree_level", "current_degree_level"])

        for key in candidates:
            if key in profile and profile[key] is not None:
                return profile[key]
        return _MISSING


class _Missing:
    """Sentinel distinguishing "absent fact" from a legitimate ``None`` value."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<MISSING>"


_MISSING = _Missing()


def summarize(assessment: Assessment) -> dict[str, Any]:
    """Human-readable summary of an assessment, used by the API and exports."""
    counts = assessment.counts
    return {
        "overall_status": assessment.overall_status.value,
        "confirmed_matches": counts[Verdict.SATISFIED.value],
        "confirmed_failures": counts[Verdict.NOT_SATISFIED.value],
        "unknowns": counts[Verdict.UNKNOWN.value],
        "needs_review": counts[Verdict.NEEDS_REVIEW.value],
        "missing_fields": assessment.missing_fields,
    }


def iter_rule_kinds(rules: Iterable[Rule]) -> set[str]:
    """Helper: the set of rule kinds present in a rule set (used by eval reporting)."""
    return {rule.kind for rule in rules}
