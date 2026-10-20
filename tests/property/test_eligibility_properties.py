"""Property-based tests for the eligibility engine.

Hypothesis generates arbitrary rule sets and student profiles, and the tests
assert the invariants the engine promises (see the module docstring of
``scholarmind.eligibility.engine`` and ``docs/EVALUATION.md``):

* **P1** A missing profile fact never yields ``satisfied``; a non-ambiguous rule
  whose fact is missing yields ``unknown``.
* **P2** ``not_satisfied`` and ``satisfied`` cannot both occur for the same rule
  under a single profile.
* **P3** The engine is deterministic under permutation of the rule order.
* **P4** ``overall_status`` is ``not_eligible`` if any mandatory rule is
  ``not_satisfied``.
* **P5** ``overall_status`` is ``unknown`` (never ``eligible``) if a mandatory
  rule is ``unknown`` and no mandatory rule fails.
* **P6** ``missing_fields`` lists every unknown rule's subject, without
  duplicates.

The generator deliberately produces profiles with absent keys and ``None``
values, ambiguous rules, and comparisons between mismatched types (a string GPA
against a numeric threshold), because those are the cases that historically
produced false "you are eligible" answers.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from scholarmind.eligibility.engine import (
    Comparator,
    EligibilityEngine,
    OverallStatus,
    Rule,
    RuleComparability,
    Verdict,
)

# --- generation vocabulary ------------------------------------------------

SUBJECTS: tuple[str, ...] = (
    "nationality",
    "residency",
    "citizenship",
    "degree_level",
    "current_degree_level",
    "gpa",
    "gpa.min_overall",
    "age",
    "work_experience_months",
    "field_of_study",
    "languages",
)

KINDS: tuple[str, ...] = (
    "nationality",
    "residency",
    "degree_level",
    "gpa",
    "age",
    "work_experience",
    "generic",
)

# Comparators whose operands cannot raise for any generated fact shape.
SAFE_COMPARATORS: tuple[Comparator, ...] = (
    Comparator.EQUALS,
    Comparator.NOT_EQUALS,
    Comparator.IN,
    Comparator.NOT_IN,
    Comparator.REQUIRED,
    Comparator.ABSENT,
)

_NUMBERS = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(
        min_value=-1e6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
)

_SCALARS = st.one_of(
    st.none(),
    st.text(max_size=16),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(
        min_value=-1e6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.booleans(),
)

_LISTS = st.lists(st.text(max_size=8), max_size=3)

_FACTS = st.one_of(_SCALARS, _LISTS)


def _values_for(comparator: Comparator) -> st.SearchStrategy[Any]:
    """Strategy for the rule value matching a comparator's operand shape."""
    if comparator in (Comparator.GTE, Comparator.LTE):
        return _NUMBERS
    if comparator is Comparator.BETWEEN:
        return st.lists(_NUMBERS, min_size=2, max_size=2)
    if comparator in (Comparator.IN, Comparator.NOT_IN):
        return st.lists(st.text(max_size=8), max_size=4)
    if comparator is Comparator.CONTAINS:
        return st.text(max_size=8)
    if comparator in (Comparator.REQUIRED, Comparator.ABSENT):
        return st.booleans()
    return _SCALARS


@st.composite
def rule_strategy(draw: Any, *, safe: bool = False) -> Rule:
    """Build an arbitrary rule."""
    comparator = draw(
        st.sampled_from(SAFE_COMPARATORS if safe else list(Comparator))
    )
    return Rule(
        kind=draw(st.sampled_from(KINDS)),
        subject=draw(st.sampled_from(SUBJECTS)),
        comparator=comparator,
        value=draw(_values_for(comparator)),
        comparability=draw(st.sampled_from(list(RuleComparability))),
        rule_text=draw(st.text(max_size=40)),
        evidence_ids=(),
        ambiguous=False if safe else draw(st.booleans()),
    )


@st.composite
def profile_strategy(draw: Any) -> dict[str, Any]:
    """Build a profile with arbitrary keys; keys may be absent or ``None``."""
    keys = draw(
        st.lists(
            st.sampled_from(SUBJECTS + ("current_degree_level",)),
            min_size=0,
            max_size=len(SUBJECTS),
            unique=True,
        )
    )
    return {key: draw(_FACTS) for key in keys}


# --- helpers mirroring the engine's documented resolution rules -----------


def _candidate_fields(rule: Rule) -> list[str]:
    """Profile fields the engine may read for a rule, in resolution order."""
    if "." in rule.subject:
        head, tail = rule.subject.split(".", 1)
        return [rule.subject, head, tail]
    candidates = [rule.subject]
    if rule.kind == "nationality":
        candidates.extend(["nationality", "residency", "citizenship"])
    elif rule.kind == "residency":
        candidates.extend(["residency", "nationality"])
    elif rule.kind == "degree_level":
        candidates.extend(["degree_level", "current_degree_level"])
    return candidates


def _fact_is_missing(rule: Rule, profile: dict[str, Any]) -> bool:
    """True when no candidate field holds a usable fact for the rule."""
    return all(
        key not in profile or profile[key] is None for key in _candidate_fields(rule)
    )


def _rule_identity(rule: Rule) -> tuple[Any, ...]:
    """Identity of a rule definition, used to group verdicts in P2."""
    return (
        rule.kind,
        rule.subject,
        rule.comparator.value,
        repr(rule.value),
        rule.comparability.value,
        rule.ambiguous,
    )


def _evaluate(rules: list[Rule], profile: dict[str, Any]) -> Any:
    """Evaluate rules against a profile with the default engine."""
    engine = EligibilityEngine()
    return engine.evaluate(cycle_id="cycle-prop", rules=rules, profile=profile)


# --- P1: a missing fact is never a satisfied rule -------------------------


@settings(max_examples=100, deadline=None)
@example(
    rules=[
        Rule(
            kind="gpa",
            subject="gpa.min_overall",
            comparator=Comparator.GTE,
            value=3.0,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must hold at least a 3.0 GPA.",
            evidence_ids=("ev_1",),
        )
    ],
    profile={},
)
@example(
    rules=[
        Rule(
            kind="gpa",
            subject="gpa.min_overall",
            comparator=Comparator.GTE,
            value=3.0,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must hold at least a 3.0 GPA.",
            evidence_ids=("ev_1",),
        )
    ],
    profile={"gpa": None},
)
@example(
    rules=[
        Rule(
            kind="nationality",
            subject="nationality",
            comparator=Comparator.IN,
            value=["GHA", "NGA"],
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must be nationals of Ghana or Nigeria.",
            evidence_ids=("ev_2",),
        )
    ],
    profile={"nationality": "GHA"},
)
@example(
    rules=[
        Rule(
            kind="gpa",
            subject="gpa.min_overall",
            comparator=Comparator.GTE,
            value=3.0,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must hold at least a 3.0 GPA.",
            evidence_ids=("ev_1",),
        )
    ],
    profile={"gpa": "3.5"},
)
@given(rules=st.lists(rule_strategy(), max_size=6), profile=profile_strategy())
def test_missing_fact_is_never_satisfied(rules: list[Rule], profile: dict[str, Any]) -> None:
    """P1: an unresolvable fact yields ``unknown`` (or ``needs_review``), never ``satisfied``."""
    assessment = _evaluate(rules, profile)

    for result in assessment.results:
        if not _fact_is_missing(result.rule, profile):
            continue
        assert result.verdict is not Verdict.SATISFIED
        if not result.rule.ambiguous:
            assert result.verdict is Verdict.UNKNOWN
            assert result.missing_field == result.rule.subject


# --- P2: no contradictory verdicts for one rule ---------------------------


@settings(max_examples=100, deadline=None)
@example(
    rules=[
        Rule(
            kind="gpa",
            subject="gpa.min_overall",
            comparator=Comparator.GTE,
            value=3.0,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must hold at least a 3.0 GPA.",
            evidence_ids=("ev_1",),
        )
    ],
    profile={"gpa": 3.5},
)
@given(rules=st.lists(rule_strategy(), max_size=8), profile=profile_strategy())
def test_satisfied_and_not_satisfied_never_coexist(rules: list[Rule], profile: dict[str, Any]) -> None:
    """P2: a single rule definition yields at most one of the two confident verdicts."""
    assessment = _evaluate(rules, profile)

    by_definition: dict[tuple[Any, ...], set[Verdict]] = {}
    for result in assessment.results:
        by_definition.setdefault(_rule_identity(result.rule), set()).add(result.verdict)

    for verdicts in by_definition.values():
        assert not (Verdict.SATISFIED in verdicts and Verdict.NOT_SATISFIED in verdicts)


# --- P3: order independence -----------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    rules=st.lists(rule_strategy(), max_size=8),
    profile=profile_strategy(),
    order=st.data(),
)
def test_rule_order_does_not_change_the_outcome(
    rules: list[Rule], profile: dict[str, Any], order: st.DataObject
) -> None:
    """P3: permuting the rules yields the same verdicts and the same overall status."""
    shuffled = list(order.draw(st.permutations(rules)))
    assert sorted(id(rule) for rule in shuffled) == sorted(id(rule) for rule in rules)

    baseline = _evaluate(rules, profile)
    permuted = _evaluate(shuffled, profile)

    baseline_by_rule = {
        id(rule): result.verdict for rule, result in zip(rules, baseline.results, strict=True)
    }
    permuted_by_rule = {
        id(rule): result.verdict
        for rule, result in zip(shuffled, permuted.results, strict=True)
    }
    assert baseline_by_rule == permuted_by_rule

    assert Counter(result.verdict for result in baseline.results) == Counter(
        result.verdict for result in permuted.results
    )
    assert baseline.overall_status is permuted.overall_status


# --- P4: a mandatory failure is decisive ----------------------------------


@settings(max_examples=100, deadline=None)
@example(
    rules=[
        Rule(
            kind="nationality",
            subject="nationality",
            comparator=Comparator.EQUALS,
            value="NGA",
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must be Nigerian nationals.",
            evidence_ids=("ev_1",),
        )
    ],
    profile={"nationality": "GHA"},
)
@given(rules=st.lists(rule_strategy(), max_size=8), profile=profile_strategy())
def test_mandatory_failure_yields_not_eligible(rules: list[Rule], profile: dict[str, Any]) -> None:
    """P4: any mandatory ``not_satisfied`` makes the assessment ``not_eligible``."""
    assessment = _evaluate(rules, profile)

    mandatory_failures = [
        result
        for result in assessment.results
        if result.rule.comparability is RuleComparability.MANDATORY
        and result.verdict is Verdict.NOT_SATISFIED
    ]
    if mandatory_failures:
        assert assessment.overall_status is OverallStatus.NOT_ELIGIBLE


# --- P5: an unknown mandatory rule blocks eligibility ---------------------


@settings(max_examples=100, deadline=None)
@example(
    rules=[
        Rule(
            kind="gpa",
            subject="gpa.min_overall",
            comparator=Comparator.GTE,
            value=3.0,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must hold at least a 3.0 GPA.",
            evidence_ids=("ev_1",),
        )
    ],
    profile={},
)
@given(
    rules=st.lists(rule_strategy(safe=True), max_size=6),
    profile=profile_strategy(),
)
def test_unknown_mandatory_rule_yields_unknown(rules: list[Rule], profile: dict[str, Any]) -> None:
    """P5: an unknown mandatory rule (with no mandatory failure) yields ``unknown``."""
    assessment = _evaluate(rules, profile)

    mandatory = [
        result for result in assessment.results if result.rule.comparability is RuleComparability.MANDATORY
    ]
    has_unknown = any(result.verdict is Verdict.UNKNOWN for result in mandatory)
    has_failure = any(result.verdict is Verdict.NOT_SATISFIED for result in mandatory)
    if has_unknown and not has_failure:
        assert assessment.overall_status is OverallStatus.UNKNOWN
    elif has_unknown:
        assert assessment.overall_status is OverallStatus.NOT_ELIGIBLE


# --- P6: missing fields are complete and unique ---------------------------


@settings(max_examples=100, deadline=None)
@example(
    rules=[
        Rule(
            kind="gpa",
            subject="gpa.min_overall",
            comparator=Comparator.GTE,
            value=3.0,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must hold at least a 3.0 GPA.",
            evidence_ids=("ev_1",),
        ),
        Rule(
            kind="age",
            subject="age",
            comparator=Comparator.LTE,
            value=35,
            comparability=RuleComparability.MANDATORY,
            rule_text="Applicants must be under 35.",
            evidence_ids=("ev_2",),
        ),
    ],
    profile={},
)
@given(rules=st.lists(rule_strategy(), max_size=8), profile=profile_strategy())
def test_missing_fields_lists_every_unknown_subject(
    rules: list[Rule], profile: dict[str, Any]
) -> None:
    """P6: ``missing_fields`` covers every unknown rule's subject, without duplicates."""
    assessment = _evaluate(rules, profile)

    expected = {
        result.rule.subject
        for result in assessment.results
        if result.verdict is Verdict.UNKNOWN
    }
    listed = assessment.missing_fields

    assert set(listed) == expected
    assert len(listed) == len(set(listed))
