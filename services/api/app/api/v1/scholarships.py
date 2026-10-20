"""Scholarship catalogue endpoints.

Reads are served from the structured tables. Every response carries the source
status (canonical source, trust tier, last check) so the UI can show whether the
information is fresh, stale or in conflict.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.session import get_db

router = APIRouter(prefix="/scholarships", tags=["scholarships"])

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


@router.get("")
async def list_scholarships(
    session: Session = Depends(get_db),
    search: str | None = Query(default=None, description="Free-text search over name and description"),
    provider_type: str | None = None,
    trust_tier: str | None = None,
    country: str | None = Query(default=None, description="ISO alpha-3 destination country code"),
    field: str | None = Query(default=None, description="Internal field code"),
    study_level: str | None = None,
    cycle_year: int | None = None,
    status: str | None = Query(default=None, description="Cycle status: upcoming, open, closed, undetermined"),
    funding_component: str | None = Query(default=None, description="tuition, stipend, travel, accommodation, insurance"),
    verified_only: bool = Query(default=False, description="Only cycles whose deadline is confirmed"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Search and filter the scholarship catalogue."""
    conditions = ["s.status = 'active'"]
    params: dict[str, Any] = {}

    if search:
        conditions.append("(s.name ILIKE :search OR s.description ILIKE :search)")
        params["search"] = f"%{search}%"
    if provider_type:
        conditions.append("s.provider_type = :provider_type")
        params["provider_type"] = provider_type
    if trust_tier:
        conditions.append("s.trust_tier = :trust_tier")
        params["trust_tier"] = trust_tier
    if country:
        conditions.append("s.destinations::text ILIKE :country")
        params["country"] = f"%{country}%"
    if field:
        conditions.append("s.fields_of_study::text ILIKE :field")
        params["field"] = f"%{field}%"
    if study_level:
        conditions.append("s.study_levels::text ILIKE :study_level")
        params["study_level"] = f"%{study_level}%"
    if cycle_year:
        conditions.append("c.intake_year = :cycle_year")
        params["cycle_year"] = cycle_year
    if status:
        conditions.append("c.status = :status")
        params["status"] = status
    if verified_only:
        conditions.append("c.deadline_at IS NOT NULL AND c.status_confidence = 'confirmed'")
    if funding_component:
        conditions.append(
            """
            EXISTS (
                SELECT 1 FROM funding_components fc
                WHERE fc.cycle_id = c.id AND fc.component = :funding_component
                  AND fc.coverage_status IN ('included', 'conditional')
            )
            """
        )
        params["funding_component"] = funding_component

    where = " AND ".join(conditions)
    params["limit"] = limit
    params["offset"] = offset

    rows = session.execute(
        text(
            f"""
            SELECT s.id::text, s.slug, s.name, s.provider_type, s.provider_name,
                   s.provider_country_iso3, s.study_levels, s.fields_of_study, s.destinations,
                   s.trust_tier, s.website_url, d.url AS source_url, d.last_success_at,
                   d.last_checked_at, d.fetch_status,
                   c.id::text AS cycle_id, c.intake_year, c.cycle_label, c.deadline_at,
                   c.deadline_raw_text, c.deadline_precision, c.status AS cycle_status,
                   c.status_confidence, c.opens_at
            FROM scholarships s
            JOIN source_documents d ON d.id = s.canonical_source_id
            LEFT JOIN scholarship_cycles c ON c.scholarship_id = s.id AND c.is_current = true
            WHERE {where}
            ORDER BY (c.deadline_at IS NULL), c.deadline_at ASC, s.name ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).fetchall()

    total = session.execute(
        text(f"SELECT count(*) FROM scholarships s LEFT JOIN scholarship_cycles c ON c.scholarship_id = s.id AND c.is_current = true WHERE {where}"),
        {key: value for key, value in params.items() if key not in ("limit", "offset")},
    ).scalar_one()

    items = [
        {
            "id": row[0],
            "slug": row[1],
            "name": row[2],
            "provider_type": row[3],
            "provider_name": row[4],
            "provider_country": row[5],
            "study_levels": row[6],
            "fields_of_study": row[7],
            "destinations": row[8],
            "trust_tier": row[9],
            "website_url": row[10],
            "source_url": row[11],
            "source_last_checked_at": row[12].isoformat() if row[12] else None,
            "source_last_success_at": row[13].isoformat() if row[13] else None,
            "source_fetch_status": row[14],
            "cycle": (
                {
                    "id": row[15],
                    "intake_year": row[16],
                    "label": row[17],
                    "deadline": row[18].isoformat() if row[18] else None,
                    "deadline_raw_text": row[19],
                    "deadline_precision": row[20],
                    "status": row[21],
                    "status_confidence": row[22],
                    "opens_at": row[23].isoformat() if row[23] else None,
                }
                if row[15]
                else None
            ),
        }
        for row in rows
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


@router.get("/{scholarship_id}")
async def scholarship_detail(scholarship_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    """The full record of one scholarship, with cycles and source status."""
    row = session.execute(
        text(
            """
            SELECT s.id::text, s.slug, s.name, s.provider_type, s.provider_name,
                   s.provider_country_iso3, s.description, s.study_levels, s.fields_of_study,
                   s.destinations, s.trust_tier, s.website_url, s.status,
                   d.id::text, d.url, d.trust_tier, d.last_checked_at, d.last_success_at,
                   d.fetch_status, d.refresh_cadence_hours
            FROM scholarships s
            JOIN source_documents d ON d.id = s.canonical_source_id
            WHERE s.id::text = :id OR s.slug = :id
            """
        ),
        {"id": scholarship_id},
    ).fetchone()
    if not row:
        raise NotFoundError(f"Scholarship '{scholarship_id}' was not found.")

    cycles = session.execute(
        text(
            """
            SELECT id::text, intake_year, cycle_label, opens_at, deadline_at, deadline_raw_text,
                   deadline_precision, status, status_confidence, is_current
            FROM scholarship_cycles
            WHERE scholarship_id::text = :id
            ORDER BY intake_year DESC
            """
        ),
        {"id": row[0]},
    ).fetchall()

    funding = session.execute(
        text(
            """
            SELECT fc.component, fc.coverage_status, fc.amount, fc.currency, fc.amount_period,
                   fc.conditions, c.intake_year
            FROM funding_components fc
            JOIN scholarship_cycles c ON c.id = fc.cycle_id
            WHERE c.scholarship_id::text = :id
            ORDER BY c.intake_year DESC, fc.component
            """
        ),
        {"id": row[0]},
    ).fetchall()

    documents = session.execute(
        text(
            """
            SELECT rd.doc_type, rd.is_mandatory, rd.description, rd.lead_time_days,
                   rd.requires_notarization, rd.requires_apostille, rd.requires_credential_evaluation,
                   c.intake_year
            FROM required_documents rd
            JOIN scholarship_cycles c ON c.id = rd.cycle_id
            WHERE c.scholarship_id::text = :id
            ORDER BY c.intake_year DESC, rd.doc_type
            """
        ),
        {"id": row[0]},
    ).fetchall()

    rules = session.execute(
        text(
            """
            SELECT r.kind, r.subject, r.operator, r.value, r.comparator, r.rule_text,
                   r.confidence, r.ambiguity_flag, r.evidence_ids, c.intake_year
            FROM eligibility_rules r
            JOIN scholarship_cycles c ON c.id = r.cycle_id
            WHERE c.scholarship_id::text = :id
            ORDER BY c.intake_year DESC, r.kind
            """
        ),
        {"id": row[0]},
    ).fetchall()

    return {
        "id": row[0],
        "slug": row[1],
        "name": row[2],
        "provider_type": row[3],
        "provider_name": row[4],
        "provider_country": row[5],
        "description": row[6],
        "study_levels": row[7],
        "fields_of_study": row[8],
        "destinations": row[9],
        "trust_tier": row[10],
        "website_url": row[11],
        "status": row[12],
        "source": {
            "id": row[13],
            "url": row[14],
            "trust_tier": row[15],
            "last_checked_at": row[16].isoformat() if row[16] else None,
            "last_success_at": row[17].isoformat() if row[17] else None,
            "fetch_status": row[18],
            "refresh_cadence_hours": row[19],
        },
        "cycles": [
            {
                "id": cycle[0],
                "intake_year": cycle[1],
                "label": cycle[2],
                "opens_at": cycle[3].isoformat() if cycle[3] else None,
                "deadline": cycle[4].isoformat() if cycle[4] else None,
                "deadline_raw_text": cycle[5],
                "deadline_precision": cycle[6],
                "status": cycle[7],
                "status_confidence": cycle[8],
                "is_current": cycle[9],
            }
            for cycle in cycles
        ],
        "funding_components": [
            {
                "component": item[0],
                "coverage_status": item[1],
                "amount": float(item[2]) if item[2] is not None else None,
                "currency": item[3],
                "amount_period": item[4],
                "conditions": item[5],
                "intake_year": item[6],
            }
            for item in funding
        ],
        "required_documents": [
            {
                "doc_type": item[0],
                "mandatory": item[1],
                "description": item[2],
                "lead_time_days": item[3],
                "requires_notarization": item[4],
                "requires_apostille": item[5],
                "requires_credential_evaluation": item[6],
                "intake_year": item[7],
            }
            for item in documents
        ],
        "eligibility_rules": [
            {
                "kind": item[0],
                "subject": item[1],
                "operator": item[2],
                "value": item[3],
                "comparability": item[4],
                "rule_text": item[5],
                "confidence": item[6],
                "ambiguous": item[7],
                "evidence_ids": item[8] or [],
                "intake_year": item[9],
            }
            for item in rules
        ],
    }


@router.get("/{scholarship_id}/history")
async def scholarship_history(scholarship_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Change history and open conflicts for a scholarship."""
    changes = session.execute(
        text(
            """
            SELECT ce.id::text, ce.field_name, ce.old_value, ce.new_value, ce.change_type,
                   ce.severity, ce.detected_at, ce.review_status, ce.review_note, ce.cycle_id::text
            FROM change_events ce
            JOIN source_documents d ON d.id = ce.source_document_id
            WHERE d.id::text = :source_id
               OR ce.cycle_id IN (
                   SELECT id FROM scholarship_cycles WHERE scholarship_id::text = :id
               )
            ORDER BY ce.detected_at DESC
            LIMIT 200
            """
        ),
        {"id": scholarship_id, "source_id": scholarship_id},
    ).fetchall()

    conflicts = session.execute(
        text(
            """
            SELECT id::text, field_name, value_a, value_b, source_document_id_a::text,
                   source_document_id_b::text, status, created_at
            FROM conflicts
            WHERE entity_type = 'scholarship_cycles'
              AND entity_id IN (SELECT id FROM scholarship_cycles WHERE scholarship_id::text = :id)
            ORDER BY created_at DESC
            """
        ),
        {"id": scholarship_id},
    ).fetchall()

    return {
        "changes": [
            {
                "id": item[0],
                "field": item[1],
                "old_value": item[2],
                "new_value": item[3],
                "change_type": item[4],
                "severity": item[5],
                "detected_at": item[6].isoformat() if item[6] else None,
                "review_status": item[7],
                "review_note": item[8],
                "cycle_id": item[9],
            }
            for item in changes
        ],
        "conflicts": [
            {
                "id": item[0],
                "field": item[1],
                "value_a": item[2],
                "value_b": item[3],
                "source_a": item[4],
                "source_b": item[5],
                "status": item[6],
                "created_at": item[7].isoformat() if item[7] else None,
            }
            for item in conflicts
        ],
    }


@router.get("/{scholarship_id}/evidence")
async def scholarship_evidence(scholarship_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    """The evidence claims behind a scholarship's structured facts."""
    claims = session.execute(
        text(
            """
            SELECT ec.id::text, ec.claim_text, ec.claim_type, ec.field_name, ec.normalized_value,
                   ec.validation_status, ec.confidence, ec.span_start, ec.span_end,
                   ec.extraction_method, ss.fetched_at, d.url
            FROM evidence_claims ec
            JOIN source_snapshots ss ON ss.id = ec.snapshot_id
            JOIN source_documents d ON d.id = ss.source_document_id
            WHERE d.id::text = :source_id
               OR ec.subject_id::text = :id
            ORDER BY ec.confidence DESC
            LIMIT 200
            """
        ),
        {"id": scholarship_id, "source_id": scholarship_id},
    ).fetchall()

    return {
        "claims": [
            {
                "id": item[0],
                "text": item[1],
                "claim_type": item[2],
                "field": item[3],
                "value": item[4],
                "validation_status": item[5],
                "confidence": item[6],
                "span": [item[7], item[8]],
                "extraction_method": item[9],
                "snapshot_fetched_at": item[10].isoformat() if item[10] else None,
                "source_url": item[11],
            }
            for item in claims
        ]
    }
