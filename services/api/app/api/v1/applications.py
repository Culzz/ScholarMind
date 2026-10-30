"""Application tracking: the student's applications and their task checklists.

Creating an application generates its task list from the deterministic planner
(``scholarmind.planning.plan``) against that cycle's required documents and
deadline lead times. Tasks are suggestions a student accepts, reschedules or
completes; nothing is sent anywhere and no task is marked complete on the
student's behalf.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.rate_limit import rate_limit
from app.core.security import current_user
from app.db.session import get_db

router = APIRouter(prefix="/applications", tags=["applications"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])

APPLICATION_STATUSES = ("planning", "preparing", "submitted", "accepted", "rejected", "withdrawn")
TASK_STATUSES = ("todo", "in_progress", "done", "blocked", "skipped")


def _application_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "scholarship_id": row[1],
        "scholarship_name": row[2],
        "cycle_id": row[3],
        "cycle_label": row[4],
        "status": row[5],
        "target_deadline": row[6].isoformat() if row[6] else None,
        "notes": row[7],
        "task_count": row[8],
        "created_at": row[9].isoformat() if row[9] else None,
        "updated_at": row[10].isoformat() if row[10] else None,
    }


@router.get("", dependencies=[Depends(rate_limit("profile_read", setting="rate_limit_read_per_min"))])
async def list_applications(
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """The signed-in student's applications."""
    rows = session.execute(
        text(
            """
            SELECT a.id::text, a.scholarship_id::text, s.name, a.cycle_id::text,
                   c.cycle_label, a.status, a.target_deadline, a.notes,
                   (SELECT count(*) FROM application_tasks t WHERE t.application_id = a.id),
                   a.created_at, a.updated_at
            FROM applications a
            JOIN scholarships s ON s.id = a.scholarship_id
            JOIN scholarship_cycles c ON c.id = a.cycle_id
            WHERE a.user_id::text = :user_id
            ORDER BY a.created_at DESC
            LIMIT 200
            """
        ),
        {"user_id": user["sub"]},
    ).fetchall()
    return {"items": [_application_row(row) for row in rows], "next_cursor": None}


class CreateApplication(BaseModel):
    """Create an application and generate its task checklist."""

    scholarship_id: str
    cycle_id: str
    notes: str | None = Field(default=None, max_length=2000)
    target_deadline: str | None = None


@router.post("", dependencies=[Depends(rate_limit("planning_write", setting="rate_limit_write_per_min"))])
async def create_application(
    payload: CreateApplication,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Start an application for one cycle, generating the planner's tasks."""
    cycle = session.execute(
        text(
            """
            SELECT c.id::text, c.deadline_at, s.id::text, s.name
            FROM scholarship_cycles c
            JOIN scholarships s ON s.id = c.scholarship_id
            WHERE c.id::text = :cycle_id
            """
        ),
        {"cycle_id": payload.cycle_id},
    ).first()
    if not cycle:
        raise NotFoundError("Cycle not found.")
    if cycle[2] != payload.scholarship_id:
        raise ConflictError("The cycle belongs to a different scholarship.")

    existing = session.execute(
        text(
            """
            SELECT id::text FROM applications
            WHERE user_id::text = :user_id AND cycle_id::text = :cycle_id
            """
        ),
        {"user_id": user["sub"], "cycle_id": payload.cycle_id},
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An application for this cycle already exists.")

    application_id = session.execute(
        text(
            """
            INSERT INTO applications
                (id, user_id, scholarship_id, cycle_id, status, target_deadline, notes)
            VALUES (gen_random_uuid(), CAST(:user_id AS uuid), CAST(:scholarship_id AS uuid),
                    CAST(:cycle_id AS uuid), 'planning',
                    COALESCE(:target_deadline, CAST(:cycle_deadline AS timestamptz)), :notes)
            RETURNING id::text
            """
        ),
        {
            "user_id": user["sub"],
            "scholarship_id": payload.scholarship_id,
            "cycle_id": payload.cycle_id,
            "target_deadline": payload.target_deadline,
            "cycle_deadline": cycle[1].isoformat() if cycle[1] else None,
            "notes": payload.notes,
        },
    ).scalar_one()

    generated = _generate_tasks(
        session,
        application_id=application_id,
        cycle_id=payload.cycle_id,
        scholarship_id=payload.scholarship_id,
    )
    session.commit()
    return {
        "id": application_id,
        "scholarship_id": payload.scholarship_id,
        "scholarship_name": cycle[3],
        "cycle_id": payload.cycle_id,
        "status": "planning",
        "target_deadline": cycle[1].isoformat() if cycle[1] else None,
        "notes": payload.notes,
        "tasks_generated": generated,
    }


class UpdateApplication(BaseModel):
    """Partial application update."""

    status: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    target_deadline: str | None = None


@router.patch("/{application_id}", dependencies=[Depends(rate_limit("planning_write", setting="rate_limit_write_per_min"))])
async def update_application(
    application_id: str,
    payload: UpdateApplication,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Update one of the signed-in student's applications."""
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "status" in updates and updates["status"] not in APPLICATION_STATUSES:
        raise ConflictError(f"Unknown application status '{updates['status']}'.")
    set_clauses = []
    params: dict[str, Any] = {"application_id": application_id, "user_id": user["sub"]}
    for column, value in updates.items():
        if column == "target_deadline":
            set_clauses.append("target_deadline = CAST(:target_deadline AS timestamptz)")
        else:
            set_clauses.append(f"{column} = :{column}")
        params[column] = value
    if set_clauses:
        session.execute(
            text(
                f"""
                UPDATE applications SET {', '.join(set_clauses)}, updated_at = now()
                WHERE id::text = :application_id AND user_id::text = :user_id
                """
            ),
            params,
        )
    else:
        session.execute(
            text(
                """
                UPDATE applications SET updated_at = now()
                WHERE id::text = :application_id AND user_id::text = :user_id
                """
            ),
            params,
        )
    session.commit()
    if "status" in updates and updates["status"] == "submitted":
        # Mark generated submission tasks done when the student records a submission.
        session.execute(
            text(
                """
                UPDATE application_tasks t SET status = 'done', completed_at = now(), updated_at = now()
                FROM applications a
                WHERE a.id = t.application_id AND a.id::text = :application_id
                  AND a.user_id::text = :user_id AND t.task_type = 'submission' AND t.status <> 'done'
                """
            ),
            {"application_id": application_id, "user_id": user["sub"]},
        )
        session.commit()
    row = session.execute(
        text(
            """
            SELECT a.id::text, a.scholarship_id::text, s.name, a.cycle_id::text,
                   c.cycle_label, a.status, a.target_deadline, a.notes,
                   (SELECT count(*) FROM application_tasks t WHERE t.application_id = a.id),
                   a.created_at, a.updated_at
            FROM applications a
            JOIN scholarships s ON s.id = a.scholarship_id
            JOIN scholarship_cycles c ON c.id = a.cycle_id
            WHERE a.id::text = :application_id AND a.user_id::text = :user_id
            """
        ),
        {"application_id": application_id, "user_id": user["sub"]},
    ).first()
    if not row:
        raise NotFoundError("Application not found.")
    return _application_row(row)


def _generate_tasks(session: Session, *, application_id: str, cycle_id: str, scholarship_id: str) -> int:
    """Create rows for the planner's deterministically generated tasks."""
    from scholarmind.planning.plan import ApplicationPlan, RequiredDocument, PlannedTask, generate_plan

    cycle = session.execute(
        text(
            """
            SELECT deadline_at FROM scholarship_cycles WHERE id::text = :cycle_id
            """
        ),
        {"cycle_id": cycle_id},
    ).scalar_one_or_none()

    document_rows = session.execute(
        text(
            """
            SELECT rd.doc_type, rd.is_mandatory, rd.description, rd.lead_time_days,
                   rd.requires_notarization, rd.requires_apostille, rd.requires_credential_evaluation
            FROM required_documents rd WHERE rd.cycle_id::text = :cycle_id
            """
        ),
        {"cycle_id": cycle_id},
    ).fetchall()

    plan: ApplicationPlan = generate_plan(
        cycle_id=cycle_id,
        cycle_deadline=cycle,
        scholarship_id=scholarship_id,
        documents=[
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
        ],
    )

    generated = 0
    for task in plan.tasks:
        session.execute(
            text(
                """
                INSERT INTO application_tasks
                    (id, application_id, title, task_type, due_at, status, doc_type,
                     is_auto_generated, notes)
                VALUES (gen_random_uuid(), CAST(:application_id AS uuid), :title, :task_type,
                        :due_at, 'todo', :doc_type, true, :notes)
                """
            ),
            {
                "application_id": application_id,
                "title": task.title,
                "task_type": task.task_type,
                "due_at": task.due_at,
                "doc_type": task.doc_type,
                "notes": getattr(task, "notes", None),
            },
        )
        generated += 1
    return generated


def _task_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "application_id": row[1],
        "title": row[2],
        "task_type": row[3],
        "due_at": row[4].isoformat() if row[4] else None,
        "status": row[5],
        "depends_on_task_id": row[6],
        "doc_type": row[7],
        "is_auto_generated": row[8],
        "notes": row[9],
        "completed_at": row[10].isoformat() if row[10] else None,
        "created_at": row[11].isoformat() if row[11] else None,
    }


@tasks_router.get("", dependencies=[Depends(rate_limit("profile_read", setting="rate_limit_read_per_min"))])
async def list_tasks(
    application_id: str | None = None,
    status: str | None = Query(default=None),
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """The signed-in student's tasks, optionally scoped to one application."""
    clauses = ["a.user_id::text = :user_id"]
    params: dict[str, Any] = {"user_id": user["sub"]}
    if application_id:
        clauses.append("t.application_id::text = :application_id")
        params["application_id"] = application_id
    if status:
        if status not in TASK_STATUSES:
            raise NotFoundError(f"Unknown task status '{status}'.")
        clauses.append("t.status = :status")
        params["status"] = status
    where = " AND ".join(clauses)

    rows = session.execute(
        text(
            f"""
            SELECT t.id::text, t.application_id::text, t.title, t.task_type, t.due_at,
                   t.status, t.depends_on_task_id::text, t.doc_type, t.is_auto_generated,
                   t.notes, t.completed_at, t.created_at
            FROM application_tasks t
            JOIN applications a ON a.id = t.application_id
            WHERE {where}
            ORDER BY t.created_at DESC
            LIMIT 200
            """
        ),
        params,
    ).fetchall()
    return {"items": [_task_row(row) for row in rows], "next_cursor": None}


class UpdateTask(BaseModel):
    """Partial task update; a missing key keeps the stored value."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: str | None = None
    due_at: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


@tasks_router.patch("/{task_id}", dependencies=[Depends(rate_limit("planning_write", setting="rate_limit_write_per_min"))])
async def update_task(
    task_id: str,
    payload: UpdateTask,
    session: Session = Depends(get_db),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Update one of the signed-in student's tasks."""
    owned = session.execute(
        text(
            """
            SELECT t.id::text, t.status
            FROM application_tasks t
            JOIN applications a ON a.id = t.application_id
            WHERE t.id::text = :task_id AND a.user_id::text = :user_id
            """
        ),
        {"task_id": task_id, "user_id": user["sub"]},
    ).first()
    if not owned:
        raise NotFoundError("Task not found.")

    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "status" in updates and updates["status"] not in TASK_STATUSES:
        raise ConflictError(f"Unknown task status '{updates['status']}'.")
    if not updates:
        # Nothing to change; return the row as it stands.
        current = session.execute(
            text(
                """
                SELECT t.id::text, t.application_id::text, t.title, t.task_type, t.due_at,
                       t.status, t.depends_on_task_id::text, t.doc_type, t.is_auto_generated,
                       t.notes, t.completed_at, t.created_at
                FROM application_tasks t WHERE t.id::text = :task_id
                """
            ),
            {"task_id": task_id},
        ).first()
        return _task_row(current)
    # completed_at follows the *new* status: 'done' stamps it (once), any
    # other state clears it.
    new_status = updates.get("status", owned[1])

    set_clauses = []
    params: dict[str, Any] = {"task_id": task_id, "new_status": new_status}
    for column, value in updates.items():
        # SET clauses reference the target table without an alias; 'status'
        # and 'notes' also exist on applications but SET is always target-scoped.
        if column == "due_at":
            set_clauses.append("due_at = CAST(:due_at AS timestamptz)")
        else:
            set_clauses.append(f"{column} = :{column}")
        params[column] = value
    data = session.execute(
        text(
            f"""
            UPDATE application_tasks t
            SET {', '.join(set_clauses)},
                completed_at = CASE WHEN :new_status = 'done'
                                    THEN COALESCE(t.completed_at, now())
                                    ELSE NULL END,
                updated_at = now()
            FROM applications a
            WHERE t.id::text = :task_id AND a.id = t.application_id
            RETURNING t.id::text, t.application_id::text, t.title, t.task_type, t.due_at,
                      t.status, t.depends_on_task_id::text, t.doc_type, t.is_auto_generated,
                      t.notes, t.completed_at, t.created_at
            """
        ),
        params,
    ).first()
    session.commit()
    if data is None:
        raise NotFoundError("Task not found.")
    return _task_row(data)
