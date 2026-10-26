"""Eligibility evaluation endpoints.

These endpoints expose the deterministic rule engine and the intelligence built
on top of it:

* ``POST /eligibility/evaluate``  - rule-by-rule verdicts with reasons
* ``POST /eligibility/explain``    - a human-readable reasoning trace
* ``POST /eligibility/unlock``     - the profile changes that unlock the most
* ``POST /eligibility/questions``  - the single most valuable profile question

No endpoint returns a percentage match score. The response is a set of
verdicts, reasons, evidence references and open unknowns.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.rate_limit import rate_limit
from app.db.session import get_db

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


class EvaluateRequest(BaseModel):
    """Evaluate a profile against one or more cycles."""

    cycle_ids: list[str] = Field(default_factory=list)
    scholarship_ids: list[str] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    explain: bool = True


class ExplainRequest(BaseModel):
    """Explain a stored assessment."""

    assessment_id: str


class UnlockRequest(BaseModel):
    """Compute unlock paths for a profile across a shortlist."""

    cycle_ids: list[str] = Field(default_factory=list)
    scholarship_ids: list[str] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=20)


class QuestionsRequest(BaseModel):
    """Rank the profile questions by information gain."""

    cycle_ids: list[str] = Field(default_factory=list)
    scholarship_ids: list[str] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=20)


def _load_rules(session: Session, cycle_ids: list[str]) -> dict[str, list[Any]]:
    """Load the rules of the requested cycles."""
    if not cycle_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT r.cycle_id::text, r.id::text, r.kind, r.subject, r.operator, r.value,
                   r.comparator, r.rule_text, r.evidence_ids, r.confidence, r.ambiguity_flag
            FROM eligibility_rules r
            WHERE r.cycle_id::text = ANY(:ids)
            ORDER BY r.created_at
            """
        ),
        {"ids": cycle_ids},
    ).fetchall()

    from scholarmind.eligibility.engine import Comparator, Rule, RuleComparability

    rules: dict[str, list[Any]] = {}
    for row in rows:
        rules.setdefault(row[0], []).append(
            Rule(
                id=row[1],
                kind=row[2],
                subject=row[3],
                comparator=Comparator(row[4]) if row[4] in {c.value for c in Comparator} else Comparator.EQUALS,
                value=row[5],
                comparability=RuleComparability(row[6]) if row[6] in {c.value for c in RuleComparability} else RuleComparability.MANDATORY,
                rule_text=row[7] or "",
                evidence_ids=tuple(row[8] or ()),
                ambiguous=bool(row[10]),
            )
        )
    return rules


def _resolve_cycle_ids(session: Session, request: EvaluateRequest) -> list[str]:
    if request.cycle_ids:
        return request.cycle_ids
    if request.scholarship_ids:
        rows = session.execute(
            text(
                """
                SELECT c.id::text
                FROM scholarship_cycles c
                WHERE c.scholarship_id::text = ANY(:ids) AND c.is_current = true
                """
            ),
            {"ids": request.scholarship_ids},
        ).fetchall()
        return [row[0] for row in rows]
    return []


def _profile_from_session(session: Session, profile: dict[str, Any]) -> dict[str, Any]:
    """Merge the supplied profile over the stored student profile."""
    if profile:
        return profile
    try:
        rows = session.execute(
            text(
                """
                SELECT p.nationality_country_iso3, p.residency_country_iso3, p.current_degree_level,
                       p.gpa_value, p.gpa_scale, p.grade_scale_raw, p.age, p.fields_of_study,
                       p.work_experience_months, p.languages
                FROM student_profiles p
                LIMIT 1
                """
            )
        ).fetchall()
    except Exception:
        return {}
    if not rows:
        return {}
    row = rows[0]
    merged = {
        "nationality": row[0],
        "residency": row[1],
        "degree_level": row[2],
        "gpa": float(row[3]) if row[3] is not None else None,
        "gpa_scale": row[4],
        "grade_scale_raw": row[5],
        "age": row[6],
        "field_of_study": (row[7] or [None])[0] if row[7] else None,
        "work_experience_months": row[8],
        "languages": row[9] or [],
    }
    return {key: value for key, value in merged.items() if value not in (None, [], "")}


@router.post("/evaluate", dependencies=[Depends(rate_limit("eligibility_write", setting="rate_limit_write_per_min"))])
async def evaluate(payload: EvaluateRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Evaluate a profile against the rules of the selected cycles."""
    from scholarmind.eligibility.engine import EligibilityEngine, summarize

    cycle_ids = _resolve_cycle_ids(session, payload)
    if not cycle_ids:
        raise NotFoundError("No cycles matched the request.")

    rules_by_cycle = _load_rules(session, cycle_ids)
    profile = _profile_from_session(session, payload.profile)
    engine = EligibilityEngine()

    assessments: list[dict[str, Any]] = []
    for cycle_id in cycle_ids:
        rules = rules_by_cycle.get(cycle_id, [])
        assessment = engine.evaluate(cycle_id=cycle_id, rules=rules, profile=profile)
        record = assessment.to_dict()
        if not payload.explain:
            record.pop("results", None)
        record["summary"] = summarize(assessment)
        assessments.append(record)

    return {
        "profile_fields_used": sorted(profile.keys()),
        "assessments": assessments,
        "engine_version": engine.version,
    }


@router.post("/explain", dependencies=[Depends(rate_limit("eligibility_write", setting="rate_limit_write_per_min"))])
async def explain(payload: ExplainRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Explain a stored assessment rule by rule."""
    rows = session.execute(
        text(
            """
            SELECT id::text, cycle_id::text, overall_status, verdict_counts, results,
                   engine_version, ruleset_version, created_at
            FROM eligibility_assessments
            WHERE id::text = :assessment_id
            """
        ),
        {"assessment_id": payload.assessment_id},
    ).fetchall()
    if not rows:
        raise NotFoundError("Assessment not found.")

    row = rows[0]
    results = row[4] or []
    return {
        "assessment_id": row[0],
        "cycle_id": row[1],
        "overall_status": row[2],
        "verdict_counts": row[3] or {},
        "engine_version": row[5],
        "ruleset_version": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
        "explanation": [
            {
                "kind": result.get("kind"),
                "subject": result.get("subject"),
                "verdict": result.get("verdict"),
                "reason": result.get("reason"),
                "rule_text": result.get("rule_text"),
                "evidence_ids": result.get("evidence_ids") or [],
                "missing_field": result.get("missing_field"),
            }
            for result in results
        ],
    }


@router.post("/unlock", dependencies=[Depends(rate_limit("eligibility_write", setting="rate_limit_write_per_min"))])
async def unlock(payload: UnlockRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Rank the profile changes that unlock the most opportunities."""
    from scholarmind.eligibility.engine import EligibilityEngine
    from scholarmind.eligibility.unlock import CycleRules, compute_unlock_paths, describe_unlock_paths

    cycle_ids = payload.cycle_ids
    if not cycle_ids and payload.scholarship_ids:
        rows = session.execute(
            text(
                """
                SELECT id::text FROM scholarship_cycles
                WHERE scholarship_id::text = ANY(:ids) AND is_current = true
                """
            ),
            {"ids": payload.scholarship_ids},
        ).fetchall()
        cycle_ids = [row[0] for row in rows]
    if not cycle_ids:
        raise NotFoundError("No cycles matched the request.")

    rules_by_cycle = _load_rules(session, cycle_ids)
    profile = _profile_from_session(session, payload.profile)

    cycles = [
        CycleRules(cycle_id=cycle_id, rules=rules_by_cycle.get(cycle_id, []))
        for cycle_id in cycle_ids
    ]
    paths = compute_unlock_paths(
        profile=profile,
        cycles=cycles,
        engine=EligibilityEngine(),
        max_paths=payload.limit,
    )
    return {
        "paths": [path.to_dict() for path in paths],
        "summary": describe_unlock_paths(paths),
        "engine_version": EligibilityEngine.version,
    }


@router.post("/questions", dependencies=[Depends(rate_limit("eligibility_write", setting="rate_limit_write_per_min"))])
async def questions(payload: QuestionsRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Rank the profile questions by the number of unknowns they would resolve."""
    from scholarmind.eligibility.engine import EligibilityEngine
    from scholarmind.eligibility.questions import coverage_summary, next_question, rank_questions

    cycle_ids = payload.cycle_ids
    if not cycle_ids and payload.scholarship_ids:
        rows = session.execute(
            text(
                """
                SELECT id::text FROM scholarship_cycles
                WHERE scholarship_id::text = ANY(:ids) AND is_current = true
                """
            ),
            {"ids": payload.scholarship_ids},
        ).fetchall()
        cycle_ids = [row[0] for row in rows]
    if not cycle_ids:
        raise NotFoundError("No cycles matched the request.")

    rules_by_cycle = _load_rules(session, cycle_ids)
    profile = _profile_from_session(session, payload.profile)

    engine = EligibilityEngine()
    assessments = {
        cycle_id: engine.evaluate(cycle_id=cycle_id, rules=rules_by_cycle.get(cycle_id, []), profile=profile)
        for cycle_id in cycle_ids
    }

    ranked = rank_questions(profile=profile, assessments=assessments, limit=payload.limit)
    best = next_question(profile=profile, assessments=assessments)
    return {
        "questions": [question.to_dict() for question in ranked],
        "next_question": best.to_dict() if best else None,
        "coverage": coverage_summary(profile=profile, assessments=assessments),
    }
