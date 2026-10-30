"""The signed-in student's profile.

The eligibility engine reads profile fields verbatim; a missing value is never
coerced into a satisfied rule, so the update semantics are brutally simple:
whatever the client sends is stored, and absent keys keep their previous value.
``completeness`` is a count of the fields the platform can use - it measures the
profile, never the applicant's eligibility.
"""

from __future__ import annotations

import pydantic
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit
from app.core.security import current_user
from app.db.session import get_db

router = APIRouter(prefix="/profile", tags=["profile"])

# Fields that count towards completeness, with their weight. Required facts
# (nationality, degree level, intake year) weigh in more than preferences.
_WEIGHTS: dict[str, float] = {
    "nationality_country_iso3": 0.15,
    "residency_country_iso3": 0.05,
    "current_degree_level": 0.15,
    "current_institution": 0.05,
    "degree_completion_year": 0.05,
    "fields_of_study": 0.10,
    "gpa_value": 0.10,
    "gpa_scale": 0.05,
    "age": 0.05,
    "work_experience_months": 0.05,
    "languages": 0.10,
    "preferred_destinations": 0.05,
    "target_intake_year": 0.05,
}

_FILLED_PICKERS = ("fields_of_study", "languages", "preferred_destinations")


def _is_filled(column: str, value: Any) -> bool:
    if value is None:
        return False
    if column in _FILLED_PICKERS:
        return bool(value)
    if isinstance(value, (int, float, Decimal, str)):
        return str(value).strip() != ""
    return True


def _compute_completeness(row: dict[str, Any]) -> float:
    """Share of the profile fields the platform can use (0..1)."""
    total = _WEIGHTS.get("target_intake_year", 0.05) * 0.0 + sum(_WEIGHTS.values())
    if total <= 0:
        return 0.0
    filled = sum(_WEIGHTS[c] for c, value in row.items() if c in _WEIGHTS and _is_filled(c, value))
    return round(min(1.0, filled / total), 4)


def _serialise(row: Any) -> dict[str, Any]:
    payload = {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "nationality_country_iso3": row["nationality_country_iso3"],
        "residency_country_iso3": row["residency_country_iso3"],
        "current_degree_level": row["current_degree_level"],
        "current_institution": row["current_institution"],
        "degree_completion_year": row["degree_completion_year"],
        "fields_of_study": row["fields_of_study"] or [],
        "gpa_value": float(row["gpa_value"]) if row["gpa_value"] is not None else None,
        "gpa_scale": row["gpa_scale"],
        "age": row["age"],
        "work_experience_months": row["work_experience_months"],
        "languages": row["languages"] or [],
        "preferred_destinations": row["preferred_destinations"] or [],
        "preferred_study_modes": row["preferred_study_modes"] or [],
        "funding_requirements": row["funding_requirements"] or [],
        "target_intake_year": row["target_intake_year"],
        "completeness": float(row["completeness"]),
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
    return payload


class ProfileUpdate(BaseModel):
    """Partial profile update; a missing key keeps the stored value."""

    model_config = pydantic.ConfigDict(extra="forbid")

    nationality_country_iso3: str | None = Field(default=None, max_length=3)
    residency_country_iso3: str | None = Field(default=None, max_length=3)
    current_degree_level: str | None = None
    current_institution: str | None = Field(default=None, max_length=200)
    degree_completion_year: int | None = Field(default=None, ge=1980, le=2100)
    fields_of_study: list[str] | None = None
    gpa_value: float | None = Field(default=None, ge=0, le=100)
    gpa_scale: str | None = Field(default=None, max_length=30)
    age: int | None = Field(default=None, ge=14, le=99)
    work_experience_months: int | None = Field(default=None, ge=0, le=600)
    languages: list[dict[str, Any]] | None = None
    preferred_destinations: list[str] | None = None
    preferred_study_modes: list[str] | None = None
    funding_requirements: list[str] | None = None
    target_intake_year: int | None = Field(default=None, ge=2024, le=2100)


_UPDATABLE_COLUMNS = [
    "nationality_country_iso3",
    "residency_country_iso3",
    "current_degree_level",
    "current_institution",
    "degree_completion_year",
    "fields_of_study",
    "gpa_value",
    "gpa_scale",
    "age",
    "work_experience_months",
    "languages",
    "preferred_destinations",
    "preferred_study_modes",
    "funding_requirements",
    "target_intake_year",
]


def _select_row(session: Session, user_id: str) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id::text, user_id::text, nationality_country_iso3, residency_country_iso3,
                   current_degree_level, current_institution, degree_completion_year,
                   fields_of_study, gpa_value, gpa_scale, age, work_experience_months,
                   languages, preferred_destinations, preferred_study_modes,
                   funding_requirements, target_intake_year, completeness, updated_at
            FROM student_profiles
            WHERE user_id::text = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None


@router.get("", dependencies=[Depends(rate_limit("profile_read", setting="rate_limit_read_per_min"))])
async def get_profile(
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """The signed-in student's profile, or an honest empty one (completeness 0)."""
    row = _select_row(session, user["sub"])
    if row is None:
        return {
            "id": user["sub"],
            "user_id": user["sub"],
            "nationality_country_iso3": None,
            "residency_country_iso3": None,
            "current_degree_level": None,
            "current_institution": None,
            "degree_completion_year": None,
            "fields_of_study": [],
            "gpa_value": None,
            "gpa_scale": None,
            "age": None,
            "work_experience_months": None,
            "languages": [],
            "preferred_destinations": [],
            "preferred_study_modes": [],
            "funding_requirements": [],
            "target_intake_year": 2027,
            "completeness": 0.0,
        }
    serialised = _serialise(row)
    return serialised


@router.put("", dependencies=[Depends(rate_limit("profile_write", setting="rate_limit_write_per_min"))])
async def update_profile(
    payload: ProfileUpdate,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Create or update the signed-in student's profile."""
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)

    row = _select_row(session, user["sub"])
    merged: dict[str, Any] = (
        {column: row.get(column) for column in _UPDATABLE_COLUMNS} if row else {column: None for column in _UPDATABLE_COLUMNS}
    )
    merged.update(updates)
    # The jsonb pickers are NOT NULL in the schema; an absent list stays empty.
    for column in _FILLED_PICKERS + ("languages", "preferred_study_modes", "funding_requirements"):
        merged[column] = merged.get(column) or []

    completeness = _compute_completeness(merged)
    insert_params: dict[str, Any] = {"user_id": user["sub"], "completeness": completeness, **merged}
    insert_params["target_intake_year"] = insert_params.get("target_intake_year") or 2027
    if row is None:
        session.execute(
            text(
                """
                INSERT INTO student_profiles
                    (id, user_id, nationality_country_iso3, residency_country_iso3,
                     current_degree_level, current_institution, degree_completion_year,
                     fields_of_study, gpa_value, gpa_scale, age, work_experience_months,
                     languages, preferred_destinations, preferred_study_modes,
                     funding_requirements, target_intake_year, completeness)
                VALUES (gen_random_uuid(), CAST(:user_id AS uuid),
                        :nationality_country_iso3, :residency_country_iso3,
                        :current_degree_level, :current_institution, :degree_completion_year,
                        CAST(:fields_of_study AS jsonb), :gpa_value, :gpa_scale,
                        :age, :work_experience_months, CAST(:languages AS jsonb),
                        CAST(:preferred_destinations AS jsonb), CAST(:preferred_study_modes AS jsonb),
                        CAST(:funding_requirements AS jsonb),
                        COALESCE(:target_intake_year, 2027), :completeness)
                """
            ),
            insert_params,
        )
    else:
        set_clauses = []
        params: dict[str, Any] = {
            "user_id": user["sub"],
            "completeness": completeness,
        }
        for column in _UPDATABLE_COLUMNS:
            if column not in updates:
                continue
            set_clauses.append(f"{column} = :{column}")
            params[column] = updates[column]
        if set_clauses:
            params["completeness"] = completeness
            session.execute(
                text(
                    f"""
                    UPDATE student_profiles
                    SET {', '.join(set_clauses)},
                        completeness = :completeness,
                        updated_at = now()
                    WHERE user_id::text = :user_id
                    """
                ),
                params,
            )
        else:
            # Nothing to set: recompute completeness only (e.g. an empty put).
            session.execute(
                text(
                    """
                    UPDATE student_profiles SET completeness = :completeness, updated_at = now()
                    WHERE user_id::text = :user_id
                    """
                ),
                params,
            )
    session.commit()

    fresh = _select_row(session, user["sub"])
    if fresh is None:
        raise RuntimeError("profile row disappeared during update")
    serialised = _serialise(fresh)
    return {**serialised, "completeness": serialised["completeness"]}
