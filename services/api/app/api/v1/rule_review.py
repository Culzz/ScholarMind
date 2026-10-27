"""The rule review queue (admin).

Rule candidates - drafted by the LLM or the regex extractor - are proposed,
never active. A reviewer approves a candidate after reading it against its
quoted span; approval re-validates the candidate mechanically (span bounds,
span/text agreement, known kind/subject/operator, value contained in the quote)
and only then inserts an ``eligibility_rules`` row with ``authored_by =
'human'``. The engine therefore never consumes a rule a person did not sign
off, and the model never decides eligibility.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.security import current_admin
from app.db.session import get_db
from scholarmind.extraction.rule_drafter import (
    RULE_KINDS,
    validate_rule_shape,
)

admin_router = APIRouter(prefix="/admin", tags=["admin"])

VALUE_NORMALISED_NOTE = "value_normalised_by_extractor"


class CandidateEdit(BaseModel):
    """Optional reviewer edits applied before re-validation and approval."""

    kind: str | None = None
    subject: str | None = None
    operator: str | None = None
    value: Any = None
    comparator: str | None = Field(default=None, pattern="^(mandatory|optional)$")


class ApproveRequest(BaseModel):
    edits: CandidateEdit = Field(default_factory=CandidateEdit)
    note: str | None = Field(default=None, max_length=1000)


class RejectRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


def _candidate(session: Session, candidate_id: str) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT id::text, cycle_id::text, kind, subject, operator, value, comparator,
                   rule_text, span_start, span_end, span_text, status, drafted_by,
                   validation_notes
            FROM rule_candidates
            WHERE id::text = :id
            """
        ),
        {"id": candidate_id},
    ).mappings().first()
    if not row:
        raise NotFoundError("Rule candidate not found.")
    return dict(row)


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "cycle_id": row["cycle_id"],
        "kind": row["kind"],
        "subject": row["subject"],
        "operator": row["operator"],
        "value": row["value"],
        "comparator": row["comparator"],
        "rule_text": row["rule_text"],
        "span_start": row["span_start"],
        "span_end": row["span_end"],
        "span_text": row["span_text"],
        "status": row["status"],
        "drafted_by": row["drafted_by"],
        "validation_notes": row["validation_notes"] or [],
    }


@admin_router.get("/rule-candidates")
async def list_rule_candidates(
    status_filter: str = Query(default="proposed", alias="status", pattern="^(proposed|approved|rejected|all)$"),
    cycle_id: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """The reviewer's queue."""
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status_filter != "all":
        clauses.append("status = :status")
        params["status"] = status_filter
    if cycle_id:
        clauses.append("cycle_id::text = :cycle_id")
        params["cycle_id"] = cycle_id
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = session.execute(
        text(
            f"""
            SELECT id::text, cycle_id::text, kind, subject, operator, value, comparator,
                   rule_text, span_start, span_end, span_text, status, drafted_by,
                   validation_notes, model_id, confidence, created_at
            FROM rule_candidates
            {where}
            ORDER BY created_at ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return {"items": [_serialise(dict(row)) for row in rows], "status_filter": status_filter, "kind": kind}


@admin_router.post("/rule-candidates/{candidate_id}/approve")
async def approve_rule_candidate(
    candidate_id: str,
    payload: ApproveRequest,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Re-validate, then promote the candidate to an engine rule.

    Approval is itself a validation step: a candidate that no longer passes the
    mechanical checks (for example after editing its value) is refused with the
    validator's reasons, so an invalid rule can never be signed off.
    """
    row = _candidate(session, candidate_id)
    if row["status"] == "approved":
        raise ConflictError("This candidate is already approved.")
    if row["status"] == "rejected":
        raise ConflictError("A rejected candidate cannot be approved; propose it again instead.")

    edits = payload.edits
    kind = edits.kind if edits.kind is not None else row["kind"]
    subject = edits.subject if edits.subject is not None else row["subject"]
    operator = edits.operator if edits.operator is not None else row["operator"]
    comparator = edits.comparator if edits.comparator is not None else row["comparator"]
    value = edits.value if edits.value is not None else row["value"]

    values_normalised = VALUE_NORMALISED_NOTE in (row["validation_notes"] or [])
    errors = validate_rule_shape(
        kind=kind,
        subject=subject,
        operator=operator,
        value=value,
        quote=row["span_text"],
        values_normalised=values_normalised,
    )
    if errors:
        raise ConflictError("Candidate failed validation.", detail={"errors": errors})

    # Insert the engine rule (human-authored) and close the candidate atomically.
    rule_id = session.execute(
        text(
            """
            INSERT INTO eligibility_rules
                (id, cycle_id, kind, subject, operator, value, comparator, rule_text,
                 evidence_ids, source_snapshot_id, confidence, ambiguity_flag, authored_by, version)
            VALUES (gen_random_uuid(), CAST(:cycle_id AS uuid), :kind, :subject, :operator,
                    CAST(:value AS jsonb), :comparator, :rule_text, '[]'::jsonb, NULL,
                    1.0, false, 'human', 1)
            RETURNING id::text
            """
        ),
        {
            "cycle_id": row["cycle_id"],
            "kind": kind,
            "subject": subject,
            "operator": operator,
            "value": json.dumps(value) if value is not None else "null",
            "comparator": comparator,
            "rule_text": row["span_text"],
        },
    ).scalar_one()

    session.execute(
        text(
            """
            UPDATE rule_candidates
            SET status = 'approved',
                kind = :kind,
                subject = :subject,
                operator = :operator,
                value = CAST(:value AS jsonb),
                comparator = :comparator,
                reviewer_id = CAST(:reviewer_id AS uuid),
                reviewer_note = :note,
                approved_rule_id = CAST(:rule_id AS uuid),
                updated_at = now()
            WHERE id::text = :id
            """
        ),
        {
            "id": candidate_id,
            "kind": kind,
            "subject": subject,
            "operator": operator,
            "value": json.dumps(value) if value is not None else "null",
            "comparator": comparator,
            "reviewer_id": user.get("sub"),
            "note": payload.note,
            "rule_id": rule_id,
        },
    )
    session.commit()
    return {"id": candidate_id, "status": "approved", "rule_id": rule_id, "cycle_id": row["cycle_id"]}


@admin_router.post("/rule-candidates/{candidate_id}/reject")
async def reject_rule_candidate(
    candidate_id: str,
    payload: RejectRequest,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    """Reject a candidate; rejected candidates never become engine rules."""
    row = _candidate(session, candidate_id)
    if row["status"] not in ("proposed", "approved"):
        raise ConflictError(f"Candidate is already {row['status']}.")
    session.execute(
        text(
            """
            UPDATE rule_candidates
            SET status = 'rejected',
                reviewer_id = CAST(:reviewer_id AS uuid),
                reviewer_note = :note,
                updated_at = now()
            WHERE id::text = :id
            """
        ),
        {"id": candidate_id, "reviewer_id": user.get("sub"), "note": payload.note},
    )
    session.commit()
    return {"id": candidate_id, "status": "rejected"}
