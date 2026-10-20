"""Application planning.

The planner turns a scholarship cycle into a working schedule: which documents
to obtain, when each must be ready, what depends on what, and which items
depend on a third party (a registrar, a referee, an evaluation service) and so
carry more risk.

The plan is generated backwards from the application deadline. Every task keeps
its lead-time assumption so a student can see *why* a date was chosen and
adjust it.

The planner never fabricates content: it produces tasks, never a statement of
purpose, a reference letter or a CV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from scholarmind.planning.leadtimes import (
    DEFAULT_SUBMISSION_BUFFER_DAYS,
    LeadTime,
    lead_time_for,
    submission_deadline,
)

TASK_TYPES = {
    "document": "Obtain document",
    "request": "Request document",
    "form": "Complete form",
    "submission": "Submit application",
    "research": "Prepare research output",
    "other": "Task",
}


@dataclass
class PlannedTask:
    """One task in an application plan."""

    title: str
    task_type: str
    due_at: datetime | None = None
    doc_type: str | None = None
    depends_on_task_id: str | None = None
    lead_time_days: int | None = None
    notes: str = ""
    status: str = "todo"
    is_auto_generated: bool = True
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "task_type": self.task_type,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "doc_type": self.doc_type,
            "depends_on_task_id": self.depends_on_task_id,
            "lead_time_days": self.lead_time_days,
            "notes": self.notes,
            "status": self.status,
            "is_auto_generated": self.is_auto_generated,
        }


@dataclass
class ApplicationPlan:
    """A generated plan for one application."""

    cycle_id: str
    scholarship_id: str | None
    cycle_deadline: datetime | None
    internal_deadline: datetime | None
    tasks: list[PlannedTask] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "scholarship_id": self.scholarship_id,
            "cycle_deadline": self.cycle_deadline.isoformat() if self.cycle_deadline else None,
            "internal_deadline": self.internal_deadline.isoformat() if self.internal_deadline else None,
            "tasks": [task.to_dict() for task in self.tasks],
            "warnings": list(self.warnings),
            "task_count": len(self.tasks),
        }


@dataclass
class RequiredDocument:
    """A document a cycle requires."""

    doc_type: str
    mandatory: bool = True
    description: str = ""
    lead_time_days: int | None = None
    requires_notarization: bool = False
    requires_apostille: bool = False
    requires_credential_evaluation: bool = False


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def generate_plan(
    *,
    cycle_id: str,
    cycle_deadline: Any,
    documents: Sequence[RequiredDocument],
    scholarship_id: str | None = None,
    country_iso3: str | None = None,
    buffer_days: int = DEFAULT_SUBMISSION_BUFFER_DAYS,
    lead_time_overrides: dict[str, int] | None = None,
    extra_tasks: Sequence[PlannedTask] = (),
) -> ApplicationPlan:
    """Build a plan for one cycle, working backwards from the deadline."""
    deadline = _as_datetime(cycle_deadline)
    internal = submission_deadline(deadline, buffer_days=buffer_days)

    plan = ApplicationPlan(
        cycle_id=cycle_id,
        scholarship_id=scholarship_id,
        cycle_deadline=deadline,
        internal_deadline=internal,
    )

    if deadline is None:
        plan.warnings.append(
            "This cycle has no confirmed deadline yet, so no dated plan could be built. "
            "Tasks are listed without due dates and should be dated once the official "
            "deadline is published."
        )

    for index, document in enumerate(documents):
        lead: LeadTime = lead_time_for(
            document.doc_type,
            country_iso3=country_iso3,
            overrides=lead_time_overrides,
        )
        days = document.lead_time_days or lead.days

        due_at: datetime | None = None
        if internal is not None:
            due_at = internal - timedelta(days=days)

        title = f"Obtain {document.doc_type.replace('_', ' ')}"
        if document.mandatory:
            task_type = "request" if lead.depends_on_third_party else "document"
        else:
            task_type = "document"

        notes = lead.notes
        if document.requires_notarization:
            notes = (notes + " " if notes else "") + "Requires notarisation."
        if document.requires_apostille:
            notes = (notes + " " if notes else "") + "Requires an apostille."
        if document.requires_credential_evaluation:
            notes = (notes + " " if notes else "") + "Requires credential evaluation."

        task = PlannedTask(
            title=title,
            task_type=task_type,
            due_at=due_at,
            doc_type=document.doc_type,
            lead_time_days=days,
            notes=notes.strip(),
            task_id=f"t{index + 1}",
        )
        plan.tasks.append(task)

    # The statement of purpose depends on the documents it describes, so it is
    # scheduled after them and given its own preparation window.
    sop_task = PlannedTask(
        title="Draft statement of purpose / motivation letter",
        task_type="form",
        due_at=(internal - timedelta(days=21)) if internal else None,
        doc_type="sop",
        lead_time_days=21,
        notes=(
            "The system does not write this for you. It can only list what the "
            "official criteria ask for so you can cover each point."
        ),
        task_id=f"t{len(documents) + 1}",
    )
    plan.tasks.append(sop_task)

    if deadline is not None:
        submit_task = PlannedTask(
            title="Submit the application",
            task_type="submission",
            due_at=internal,
            lead_time_days=0,
            notes=(
                f"The internal deadline is {internal.date().isoformat()}, "
                f"{buffer_days} days before the official deadline."
            ),
            task_id=f"t{len(documents) + 2}",
        )
        plan.tasks.append(submit_task)

    plan.tasks.extend(extra_tasks)

    risky = [task for task in plan.tasks if task.doc_type in {"lor", "transcript", "credential_evaluation", "nysc"}]
    if risky:
        plan.warnings.append(
            "Some tasks depend on a third party (a referee, a registrar or an evaluation "
            "service). Start those first."
        )
    return plan


def sort_tasks(tasks: Iterable[PlannedTask]) -> list[PlannedTask]:
    """Order tasks by due date, undated tasks last."""
    return sorted(tasks, key=lambda task: (task.due_at is None, task.due_at or datetime.max.replace(tzinfo=timezone.utc)))


def task_dependencies(tasks: Sequence[PlannedTask]) -> dict[str, list[str]]:
    """Map each task to the tasks it depends on."""
    return {task.task_id or task.title: [task.depends_on_task_id] if task.depends_on_task_id else [] for task in tasks}


def critical_path(tasks: Sequence[PlannedTask]) -> list[PlannedTask]:
    """The tasks that cannot slip, ordered by how early they are due."""
    dated = [task for task in tasks if task.due_at is not None]
    return sorted(dated, key=lambda task: task.due_at)  # type: ignore[arg-type]
