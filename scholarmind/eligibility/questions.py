"""Smart Question Engine.

Asking a student for fifteen profile fields up front is how onboarding dies.
This module asks for **one** field at a time — the field whose answer resolves
the most open questions across the student's shortlist.

Information gain for a candidate question is the number of distinct rules across
the shortlist whose verdict would change from ``unknown`` once the field is
known, weighted by how consequential the rule is (a mandatory nationality rule
matters more than an optional preference rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from scholarmind.eligibility.engine import Rule, Verdict

# Questions a student can actually answer, in the wording shown to them.
QUESTION_TEMPLATES: dict[str, str] = {
    "nationality": "What is your nationality?",
    "residency": "Which country do you currently live in?",
    "degree_level": "What is the highest degree you hold (or are completing)?",
    "gpa": "What is your most recent GPA, and what is the scale (e.g. 4.0, 5.0, or a percentage)?",
    "cgpa": "What is your most recent CGPA, and what is the scale (e.g. 4.0 or 5.0)?",
    "grade_scale_raw": "How was your degree graded (First Class, Second Class Upper, CGPA 4.0, percentage)?",
    "age": "How old are you?",
    "field_of_study": "What is your field of study?",
    "work_experience_months": "How many months of work experience do you have?",
    "ielts": "What is your IELTS score?",
    "toefl": "What is your TOEFL score?",
    "languages": "Which languages can you study in?",
    "current_institution": "Which institution did you study at?",
    "degree_completion_year": "In what year did you complete (or will you complete) your degree?",
    "preferred_destinations": "Which countries would you like to study in?",
}

# How much a rule matters when deciding which question to ask next.
RULE_IMPORTANCE: dict[str, float] = {
    "nationality": 3.0,
    "residency": 2.0,
    "degree_level": 3.0,
    "gpa": 2.5,
    "cgpa": 2.5,
    "grade_scale_raw": 2.0,
    "age": 2.0,
    "field_of_study": 1.5,
    "language": 3.0,
    "work_experience": 1.0,
    "document_required": 1.0,
    "funding_requirement": 1.5,
    "course_requirement": 1.0,
    "application_prerequisite": 1.0,
}


@dataclass
class ProfileQuestion:
    """A question to ask the student, with the reason it is being asked."""

    field: str
    question: str
    information_gain: float
    affected_rule_count: int
    affected_cycle_ids: list[str] = field(default_factory=list)
    affected_rule_kinds: list[str] = field(default_factory=list)
    already_answered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "question": self.question,
            "information_gain": self.information_gain,
            "affected_rule_count": self.affected_rule_count,
            "affected_cycle_ids": list(self.affected_cycle_ids),
            "affected_rule_kinds": list(self.affected_rule_kinds),
            "already_answered": self.already_answered,
        }


def _rule_field(rule: Rule) -> str | None:
    """The profile field a rule depends on."""
    subject = rule.subject
    head = subject.split(".")[0] if "." in subject else subject
    if subject.startswith("ielts") or head == "ielts":
        return "ielts"
    if subject.startswith("toefl") or head == "toefl":
        return "toefl"
    if head in ("gpa", "cgpa", "grade"):
        return "gpa"
    if head == "age":
        return "age"
    if head == "work_experience" or subject.startswith("work_experience"):
        return "work_experience_months"
    if head == "degree_level":
        return "degree_level"
    if head == "field_of_study":
        return "field_of_study"
    if head == "nationality":
        return "nationality"
    if head == "residency":
        return "residency"
    if head == "language":
        return "ielts"
    return None


def _unknown_rule_ids(results: Sequence[Any]) -> set[str]:
    """Identifiers of rules whose verdict is currently unknown."""
    return {
        result.rule.id
        for result in results
        if result.verdict is Verdict.UNKNOWN and result.rule.id
    }


def rank_questions(
    *,
    profile: Mapping[str, Any],
    assessments: Mapping[str, Any],
    limit: int = 5,
) -> list[ProfileQuestion]:
    """Rank the profile questions by the information they would unlock.

    Parameters
    ----------
    profile:
        The facts the student has already provided.
    assessments:
        Mapping of cycle id -> assessment (an object exposing ``results``).
    """
    scores: dict[str, dict[str, Any]] = {}

    for cycle_id, assessment in assessments.items():
        unknown_ids = _unknown_rule_ids(assessment.results)
        for result in assessment.results:
            if result.rule.id not in unknown_ids:
                continue
            field = _rule_field(result.rule)
            if field is None:
                continue
            bucket = scores.setdefault(
                field,
                {"gain": 0.0, "count": 0, "cycles": set(), "kinds": set()},
            )
            importance = RULE_IMPORTANCE.get(result.rule.kind, 1.0)
            if result.rule.comparability.value == "optional":
                importance *= 0.5
            bucket["gain"] += importance
            bucket["count"] += 1
            bucket["cycles"].add(cycle_id)
            bucket["kinds"].add(result.rule.kind)

    questions: list[ProfileQuestion] = []
    for field, bucket in scores.items():
        already_answered = profile.get(field) not in (None, "", [], {})
        if already_answered:
            # The field is known but the rule is still unknown: it is an
            # ambiguous requirement, not a missing fact. It is not a question
            # the student can answer.
            continue
        questions.append(
            ProfileQuestion(
                field=field,
                question=QUESTION_TEMPLATES.get(field, f"Could you provide your {field.replace('_', ' ')}?"),
                information_gain=round(bucket["gain"], 3),
                affected_rule_count=bucket["count"],
                affected_cycle_ids=sorted(bucket["cycles"]),
                affected_rule_kinds=sorted(bucket["kinds"]),
                already_answered=already_answered,
            )
        )

    questions.sort(key=lambda question: (-question.information_gain, question.field))
    return questions[:limit]


def next_question(
    *,
    profile: Mapping[str, Any],
    assessments: Mapping[str, Any],
) -> ProfileQuestion | None:
    """The single most valuable question to ask next."""
    ranked = rank_questions(profile=profile, assessments=assessments, limit=1)
    return ranked[0] if ranked else None


def questions_for_all_unknowns(
    *,
    profile: Mapping[str, Any],
    assessments: Mapping[str, Any],
) -> list[ProfileQuestion]:
    """Every question that would resolve a currently unknown rule."""
    return rank_questions(profile=profile, assessments=assessments, limit=50)


def coverage_summary(
    *,
    profile: Mapping[str, Any],
    assessments: Mapping[str, Any],
) -> dict[str, Any]:
    """How much of the shortlist the current profile already resolves."""
    total = 0
    unknown = 0
    satisfied = 0
    for assessment in assessments.values():
        for result in assessment.results:
            total += 1
            if result.verdict is Verdict.UNKNOWN:
                unknown += 1
            elif result.verdict is Verdict.SATISFIED:
                satisfied += 1
    return {
        "rules_total": total,
        "rules_unknown": unknown,
        "rules_satisfied": satisfied,
        "resolution_rate": round(1 - (unknown / total), 3) if total else 0.0,
    }


def iter_available_fields() -> Iterable[str]:
    """The fields the engine knows how to ask about."""
    return QUESTION_TEMPLATES.keys()
