"""Comparison, recommendations and application-planning endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError, NotFoundError
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from scholarmind.planning.export import plan_to_ics, plan_to_markdown, shortlist_to_csv
from scholarmind.planning.plan import RequiredDocument, generate_plan
from scholarmind.reporting.comparison import ComparisonColumn, build_comparison, funding_row
from scholarmind.reporting.ranking import (
    describe_weights,
    normalise_weights,
    rank_opportunities,
    score_opportunity,
)

router = APIRouter(tags=["planning"])


class InvalidWeights(ApiError):
    """The ranking weights parameter could not be parsed."""

    status_code = 422
    code = "invalid_weights"


class CompareRequest(BaseModel):
    """Compare several scholarships side by side."""

    scholarship_ids: list[str] = Field(min_length=2, max_length=5)
    cycle_ids: list[str] = Field(default_factory=list)


class PlanRequest(BaseModel):
    """Build an application plan for a cycle."""

    cycle_id: str
    scholarship_id: str | None = None
    country_iso3: str | None = None
    buffer_days: int = Field(default=7, ge=0, le=60)
    lead_time_overrides: dict[str, int] = Field(default_factory=dict)


@router.post("/compare", dependencies=[Depends(rate_limit("planning_write", setting="rate_limit_write_per_min"))])
async def compare(payload: CompareRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Compare scholarships including rule-level verdicts, funding and freshness."""
    rows = session.execute(
        text(
            """
            SELECT s.id::text, s.name, s.slug, s.trust_tier, d.url, d.last_success_at,
                   c.id::text, c.intake_year, c.deadline_at, c.deadline_raw_text, c.status,
                   c.status_confidence
            FROM scholarships s
            JOIN source_documents d ON d.id = s.canonical_source_id
            LEFT JOIN scholarship_cycles c ON c.scholarship_id = s.id AND c.is_current = true
            WHERE s.id::text = ANY(:ids) OR s.slug = ANY(:ids)
            """
        ),
        {"ids": payload.scholarship_ids},
    ).fetchall()
    if not rows:
        raise NotFoundError("None of the requested scholarships were found.")

    columns: list[ComparisonColumn] = []
    conflicts: list[dict[str, Any]] = []

    for row in rows:
        column = ComparisonColumn(
            scholarship_id=row[0],
            name=row[1],
            cycle_id=row[6],
            deadline=row[8].isoformat() if row[8] else None,
            deadline_state="confirmed" if row[8] and row[10] == "confirmed" else "unresolved",
            source_url=row[4],
            source_checked_at=row[5].isoformat() if row[5] else None,
        )
        column.cells["deadline"] = funding_row(
            "deadline",
            "included" if column.deadline_state == "confirmed" else "unknown",
            value=column.deadline,
            source=row[4],
            checked_at=column.source_checked_at,
        )

        if row[6]:
            funding_rows = session.execute(
                text(
                    """
                    SELECT fc.component, fc.coverage_status, fc.amount, fc.currency, fc.conditions
                    FROM funding_components fc WHERE fc.cycle_id::text = :cycle
                    """
                ),
                {"cycle": row[6]},
            ).fetchall()
            for item in funding_rows:
                column.cells[f"funding.{item[0]}"] = funding_row(
                    item[0],
                    item[1],
                    value=(
                        f"{item[2]} {item[3]}".strip() if item[2] is not None else None
                    ),
                    source=row[4],
                    checked_at=column.source_checked_at,
                )

            rule_rows = session.execute(
                text(
                    """
                    SELECT r.kind, r.subject, r.rule_text, r.comparator, r.value, r.ambiguity_flag
                    FROM eligibility_rules r WHERE r.cycle_id::text = :cycle
                    """
                ),
                {"cycle": row[6]},
            ).fetchall()
            for item in rule_rows:
                column.cells[f"rule.{item[0]}.{item[1]}"] = funding_row(
                    item[1],
                    "unknown",
                    value=item[2],
                    source=row[4],
                    checked_at=column.source_checked_at,
                )
        columns.append(column)

    fields = sorted({key for column in columns for key in column.cells})
    comparison = build_comparison(columns=columns, fields=fields, conflicts=conflicts)
    return comparison.to_dict()


def _parse_weights(raw: str | None) -> dict[str, float]:
    """Parse the optional weights query parameter (JSON object)."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise InvalidWeights("The weights parameter must be a JSON object of factor weights.")
    if not isinstance(parsed, dict):
        raise InvalidWeights("The weights parameter must be a JSON object of factor weights.")
    cleaned: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            cleaned[str(key)] = float(value)
        except (TypeError, ValueError):
            raise InvalidWeights(f"Weight '{key}' must be a number.")
    return cleaned


@router.get("/recommendations")
async def recommendations(
    session: Session = Depends(get_db),
    weights: str | None = Query(
        default=None,
        description='JSON object of factor weights, e.g. {"deadline_urgency": 0.3, "funding_fit": 0.25}',
    ),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """Explainable personalised ranking over the current cycles."""
    normalised = normalise_weights(_parse_weights(weights))

    rows = session.execute(
        text(
            """
            SELECT s.id::text, s.name, c.id::text, c.deadline_at, c.status,
                   d.last_success_at, d.trust_tier
            FROM scholarships s
            JOIN source_documents d ON d.id = s.canonical_source_id
            JOIN scholarship_cycles c ON c.scholarship_id = s.id AND c.is_current = true
            WHERE s.status = 'active'
            ORDER BY (c.deadline_at IS NULL), c.deadline_at ASC
            LIMIT 100
            """
        )
    ).fetchall()

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    opportunities = []
    for row in rows:
        deadline = row[3]
        days = None
        if deadline is not None:
            days = (deadline - now).days
        urgency = 0.0
        if days is not None:
            if days < 0:
                urgency = 0.0
            elif days <= 30:
                urgency = 1.0
            elif days <= 90:
                urgency = 0.7
            elif days <= 180:
                urgency = 0.4
            else:
                urgency = 0.2

        freshness = 1.0 if row[5] else 0.3
        opportunities.append(
            score_opportunity(
                scholarship_id=row[0],
                name=row[1],
                cycle_id=row[2],
                deadline=deadline.isoformat() if deadline else None,
                factors={
                    "confirmed_eligibility": 0.0,
                    "deadline_urgency": urgency,
                    "funding_fit": 0.0,
                    "field_alignment": 0.0,
                    "effort": 0.5,
                    "source_freshness": freshness,
                },
                weights=normalised,
                reasons=(
                    [f"Application closes in {days} days."] if days is not None and days >= 0 else []
                ),
                blockers=(
                    ["Complete your profile to see the eligibility match for this scholarship."]
                ),
            )
        )

    ranked = rank_opportunities(opportunities, weights=normalised)[:limit]
    return {
        "items": [item.to_dict() for item in ranked],
        "weights": describe_weights(normalised),
        "interpretation": (
            "Prioritisation aid only. The score reflects the factors listed above and is not "
            "a probability of receiving an award."
        ),
    }


@router.post("/applications/plan", dependencies=[Depends(rate_limit("planning_write", setting="rate_limit_write_per_min"))])
async def build_plan(payload: PlanRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Generate an application plan for a cycle."""
    row = session.execute(
        text(
            """
            SELECT c.deadline_at, c.scholarship_id::text, s.name
            FROM scholarship_cycles c
            JOIN scholarships s ON s.id = c.scholarship_id
            WHERE c.id::text = :cycle
            """
        ),
        {"cycle": payload.cycle_id},
    ).fetchone()
    if not row:
        raise NotFoundError("Cycle not found.")

    document_rows = session.execute(
        text(
            """
            SELECT rd.doc_type, rd.is_mandatory, rd.description, rd.lead_time_days,
                   rd.requires_notarization, rd.requires_apostille, rd.requires_credential_evaluation
            FROM required_documents rd WHERE rd.cycle_id::text = :cycle
            """
        ),
        {"cycle": payload.cycle_id},
    ).fetchall()

    documents = [
        RequiredDocument(
            doc_type=item[0],
            mandatory=item[1],
            description=item[2] or "",
            lead_time_days=item[3],
            requires_notarization=item[4],
            requires_apostille=item[5],
            requires_credential_evaluation=item[6],
        )
        for item in document_rows
    ]

    plan = generate_plan(
        cycle_id=payload.cycle_id,
        cycle_deadline=row[0],
        documents=documents,
        scholarship_id=payload.scholarship_id or row[1],
        country_iso3=payload.country_iso3,
        buffer_days=payload.buffer_days,
        lead_time_overrides=payload.lead_time_overrides,
    )
    return plan.to_dict()


@router.get("/applications/plan/{cycle_id}/export")
async def export_plan(
    cycle_id: str,
    session: Session = Depends(get_db),
    format: str = Query(default="markdown", pattern="^(markdown|ics|csv)$"),
) -> PlainTextResponse:
    """Export a plan as a checklist, a calendar file or a CSV."""
    row = session.execute(
        text(
            """
            SELECT c.deadline_at, c.scholarship_id::text, s.name
            FROM scholarship_cycles c
            JOIN scholarships s ON s.id = c.scholarship_id
            WHERE c.id::text = :cycle
            """
        ),
        {"cycle": cycle_id},
    ).fetchone()
    if not row:
        raise NotFoundError("Cycle not found.")

    document_rows = session.execute(
        text("SELECT doc_type, is_mandatory, description, lead_time_days FROM required_documents WHERE cycle_id::text = :cycle"),
        {"cycle": cycle_id},
    ).fetchall()

    plan = generate_plan(
        cycle_id=cycle_id,
        cycle_deadline=row[0],
        documents=[
            RequiredDocument(doc_type=item[0], mandatory=item[1], description=item[2] or "", lead_time_days=item[3])
            for item in document_rows
        ],
        scholarship_id=row[1],
    )

    if format == "ics":
        content = plan_to_ics(plan, calendar_name=f"ScholarMind — {row[2]}")
        media_type = "text/calendar"
        filename = f"scholarmind-{cycle_id}.ics"
    elif format == "csv":
        content = shortlist_to_csv([task.to_dict() for task in plan.tasks])
        media_type = "text/csv"
        filename = f"scholarmind-{cycle_id}.csv"
    else:
        content = plan_to_markdown(plan, scholarship_name=row[2])
        media_type = "text/markdown"
        filename = f"scholarmind-{cycle_id}.md"

    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
