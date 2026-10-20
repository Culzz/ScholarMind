"""Exports: calendar, checklist and shortlist formats.

Students take these into other tools — a calendar, a document, a spreadsheet —
so the exports are plain, stable text formats rather than anything exotic.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Sequence

from scholarmind.planning.plan import ApplicationPlan, PlannedTask


def _ical_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ical_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y%m%dT%H%M%SZ")


def plan_to_ics(plan: ApplicationPlan, *, calendar_name: str = "ScholarMind application plan") -> str:
    """Render a plan as an iCalendar file."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ScholarMind//Application Plan//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ical_escape(calendar_name)}",
    ]
    for task in plan.tasks:
        if task.due_at is None:
            continue
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ical_escape(task.task_id or task.title)}@scholarmind",
                f"DTSTAMP:{_ical_timestamp(task.due_at)}",
                f"DTSTART:{_ical_timestamp(task.due_at)}",
                f"DTEND:{_ical_timestamp(task.due_at)}",
                f"SUMMARY:{_ical_escape(task.title)}",
                f"DESCRIPTION:{_ical_escape(task.notes or task.task_type)}",
                "END:VEVENT",
            ]
        )
    if plan.cycle_deadline is not None:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:deadline-{_ical_escape(plan.cycle_id)}@scholarmind",
                f"DTSTAMP:{_ical_timestamp(plan.cycle_deadline)}",
                f"DTSTART:{_ical_timestamp(plan.cycle_deadline)}",
                f"DTEND:{_ical_timestamp(plan.cycle_deadline)}",
                f"SUMMARY:{_ical_escape('Official application deadline')}",
                "DESCRIPTION:Confirm this date on the official source before relying on it.",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def plan_to_markdown(plan: ApplicationPlan, *, scholarship_name: str | None = None) -> str:
    """Render a plan as a Markdown checklist."""
    title = scholarship_name or f"Application plan — cycle {plan.cycle_id}"
    lines = [f"# {title}", ""]
    if plan.cycle_deadline:
        lines.append(f"**Official deadline:** {plan.cycle_deadline.date().isoformat()}")
    if plan.internal_deadline:
        lines.append(f"**Internal deadline:** {plan.internal_deadline.date().isoformat()}")
    lines.append("")
    if plan.warnings:
        lines.append("## Notes")
        for warning in plan.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lines.append("## Checklist")
    lines.append("")
    for task in sorted(plan.tasks, key=lambda t: (t.due_at is None, t.due_at)):
        due = task.due_at.date().isoformat() if task.due_at else "no date yet"
        checkbox = "x" if task.status == "done" else " "
        lines.append(f"- [{checkbox}] **{task.title}** — due {due}")
        if task.notes:
            lines.append(f"  - {task.notes}")
    lines.append("")
    lines.append("_Dates are planning estimates derived from document lead times; check every date against the official source._")
    return "\n".join(lines) + "\n"


def shortlist_to_csv(rows: Sequence[dict[str, Any]]) -> str:
    """Render a shortlist as CSV."""
    if not rows:
        return ""
    buffer = io.StringIO()
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def tasks_to_csv(tasks: Sequence[PlannedTask]) -> str:
    """Render plan tasks as CSV."""
    return shortlist_to_csv([task.to_dict() for task in tasks])


def plan_to_text_summary(plan: ApplicationPlan) -> str:
    """A one-screen summary for a notification or a text message."""
    dated = [task for task in plan.tasks if task.due_at is not None]
    if not dated:
        return "No dated tasks yet — the official deadline has not been published."
    ordered = sorted(dated, key=lambda task: task.due_at)
    next_task = ordered[0]
    remaining = len(ordered)
    return (
        f"{remaining} dated tasks. Next: {next_task.title} by "
        f"{next_task.due_at.date().isoformat()}."
    )
