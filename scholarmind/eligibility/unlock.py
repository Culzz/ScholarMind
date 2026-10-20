"""Unlock Paths: counterfactual eligibility.

The question a student actually asks is rarely "am I eligible?" — it is "what
should I change to become eligible?". Unlock Paths answers that by re-running
the **deterministic** rule engine against mutated profiles. No model is asked to
speculate about what would happen; every unlock is a concrete rule outcome.

For each profile field that appears in a rule, the engine tries a small set of
plausible improvements (a higher English test band, a better grade, a larger
age window) and reports which mutations flip the most rules to ``satisfied``.

Every unlock path carries the rules it changes and the evidence behind them, so
the recommendation is auditable in the same way as an eligibility verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from scholarmind.eligibility.engine import (
    Assessment,
    EligibilityEngine,
    OverallStatus,
    Rule,
    Verdict,
)

# Candidate improvements per profile field, ordered from smallest to largest
# effort. The values are deliberately conservative: they are the next band up.
CANDIDATE_IMPROVEMENTS: dict[str, tuple[tuple[Any, str], ...]] = {
    "ielts": ((6.5, "IELTS 6.5"), (7.0, "IELTS 7.0"), (7.5, "IELTS 7.5")),
    "toefl": ((90, "TOEFL 90"), (100, "TOEFL 100"), (110, "TOEFL 110")),
    "gpa": ((3.5, "GPA 3.5"), (4.0, "GPA 4.0"), (4.5, "GPA 4.5")),
    "cgpa": ((3.5, "CGPA 3.5"), (4.0, "CGPA 4.0"), (4.5, "CGPA 4.5")),
    "work_experience_months": ((12, "12 months of work experience"), (24, "24 months"), (36, "36 months")),
    "age": (),
}

# Rough effort estimates used for ranking (not promises).
EFFORT_NOTES = {
    "ielts": "Retaking the English test typically takes around 8 weeks including preparation.",
    "toefl": "Retaking the English test typically takes around 8 weeks including preparation.",
    "gpa": "Improving a grade usually means another full academic term (about 6 months).",
    "cgpa": "Improving a grade usually means another full academic term (about 6 months).",
    "work_experience_months": "Gaining work experience usually takes at least one placement cycle.",
}


@dataclass
class UnlockPath:
    """One profile change that unlocks additional opportunities."""

    subject: str
    from_value: Any
    to_value: Any
    label: str
    unlocked_cycle_ids: list[str] = field(default_factory=list)
    unlocked_count: int = 0
    rule_ids_affected: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    effort_note: str = ""
    remaining_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "label": self.label,
            "unlocked_cycle_ids": list(self.unlocked_cycle_ids),
            "unlocked_count": self.unlocked_count,
            "rule_ids_affected": list(self.rule_ids_affected),
            "evidence_ids": list(self.evidence_ids),
            "effort_note": self.effort_note,
            "remaining_blockers": list(self.remaining_blockers),
        }


@dataclass
class CycleRules:
    """The rules of one cycle, as used by the unlock computation."""

    cycle_id: str
    rules: list[Rule]


def _profile_key_for(rule: Rule) -> str | None:
    """Map a rule subject onto the profile field it depends on."""
    subject = rule.subject
    head = subject.split(".")[0] if "." in subject else subject
    if subject.startswith("ielts") or head == "ielts":
        return "ielts"
    if subject.startswith("toefl") or head == "toefl":
        return "toefl"
    if head in ("gpa", "cgpa", "grade"):
        return "gpa"
    if head == "work_experience" or subject.startswith("work_experience"):
        return "work_experience_months"
    if head == "age":
        return "age"
    return None


def _improvement_candidates(profile: Mapping[str, Any], key: str) -> list[tuple[Any, str]]:
    """Candidate new values for a profile field, above the current one."""
    if key == "gpa":
        current = profile.get("gpa") or profile.get("cgpa")
        candidates = CANDIDATE_IMPROVEMENTS["gpa"] if profile.get("gpa") is not None else CANDIDATE_IMPROVEMENTS["cgpa"]
    elif key == "work_experience_months":
        current = profile.get("work_experience_months") or 0
        candidates = CANDIDATE_IMPROVEMENTS["work_experience_months"]
    elif key == "age":
        return []
    else:
        current = profile.get(key)
        candidates = CANDIDATE_IMPROVEMENTS.get(key, ())

    if current is None:
        return []
    numeric_current = float(current)
    options: list[tuple[Any, str]] = []
    for value, label in candidates:
        if float(value) > numeric_current:
            options.append((value, label))
    return options


def compute_unlock_paths(
    *,
    profile: Mapping[str, Any],
    cycles: Sequence[CycleRules],
    engine: EligibilityEngine | None = None,
    max_paths: int = 5,
) -> list[UnlockPath]:
    """Rank the profile changes that unlock the most opportunities.

    The ranking is by number of newly unlocked cycles, then by how many rules
    the change resolves, then by the smaller required effort.
    """
    engine = engine or EligibilityEngine()
    baseline: dict[str, Assessment] = {
        cycle.cycle_id: engine.evaluate(cycle_id=cycle.cycle_id, rules=cycle.rules, profile=profile)
        for cycle in cycles
    }

    candidates: dict[str, list[tuple[Any, str]]] = {}
    for cycle in cycles:
        for rule in cycle.rules:
            key = _profile_key_for(rule)
            if key is None:
                continue
            for value, label in _improvement_candidates(profile, key):
                bucket = candidates.setdefault(key, [])
                if (value, label) not in bucket:
                    bucket.append((value, label))

    paths: list[UnlockPath] = []

    for key, options in candidates.items():
        for value, label in options:
            mutated = dict(profile)
            mutated[key] = value

            unlocked: list[str] = []
            affected_rules: list[str] = []
            evidence_ids: list[str] = []
            blockers: list[str] = []

            for cycle in cycles:
                before = baseline[cycle.cycle_id]
                after = engine.evaluate(cycle_id=cycle.cycle_id, rules=cycle.rules, profile=mutated)

                before_ok = before.overall_status in (OverallStatus.ELIGIBLE, OverallStatus.LIKELY_ELIGIBLE)
                after_ok = after.overall_status in (OverallStatus.ELIGIBLE, OverallStatus.LIKELY_ELIGIBLE)

                changed_rule_ids = [
                    result.rule.id
                    for result in after.results
                    if result.rule.id
                    and result.verdict is Verdict.SATISFIED
                    and next(
                        (
                            previous.verdict
                            for previous in before.results
                            if previous.rule.id == result.rule.id
                        ),
                        None,
                    )
                    is not Verdict.SATISFIED
                ]
                affected_rules.extend(changed_rule_ids)

                for result in after.results:
                    if result.rule.id in changed_rule_ids:
                        for evidence_id in result.evidence_ids or result.rule.evidence_ids:
                            if evidence_id not in evidence_ids:
                                evidence_ids.append(evidence_id)

                if after_ok and not before_ok:
                    unlocked.append(cycle.cycle_id)
                elif not after_ok:
                    for result in after.results:
                        if result.verdict is Verdict.NOT_SATISFIED and result.rule.comparability.value == "mandatory":
                            blockers.append(f"{cycle.cycle_id}: {result.rule.subject}")

            if unlocked:
                paths.append(
                    UnlockPath(
                        subject=key,
                        from_value=profile.get(key),
                        to_value=value,
                        label=f"Raise {label}",
                        unlocked_cycle_ids=unlocked,
                        unlocked_count=len(unlocked),
                        rule_ids_affected=sorted({rule_id for rule_id in affected_rules if rule_id}),
                        evidence_ids=evidence_ids,
                        effort_note=EFFORT_NOTES.get(key, ""),
                        remaining_blockers=sorted(set(blockers))[:5],
                    )
                )

    paths.sort(key=lambda path: (-path.unlocked_count, -len(path.rule_ids_affected), path.subject))
    return paths[:max_paths]


def describe_unlock_paths(paths: Iterable[UnlockPath]) -> str:
    """A short, human-readable summary of the best unlock path."""
    paths = list(paths)
    if not paths:
        return "No single profile change unlocks additional opportunities right now."
    best = paths[0]
    return (
        f"{best.label} unlocks {best.unlocked_count} shortlisted scholarship"
        f"{'s' if best.unlocked_count != 1 else ''}."
    )
