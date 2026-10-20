"""Document vault: what the student has, and whether it is still valid.

Scholarship applications fail on expired documents more often than on weak
statements. The vault tracks each document the student holds, its issue and
expiry dates, and warns when a document will expire before - or shortly after -
an application deadline.

Expiry rules differ by document: a passport is usually required to be valid for
six months beyond travel, while an IELTS certificate is only valid for two
years. The vault therefore compares expiry against the cycle deadline with a
per-document validity window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

# How long a document must remain valid after the application deadline.
VALIDITY_WINDOW_DAYS: dict[str, int] = {
    "passport": 180,
    "ielts": 0,
    "toefl": 0,
    "transcript": 0,
    "nysc": 0,
    "birth_certificate": 0,
    "lor": 0,
    "sop": 0,
    "cv": 0,
    "credential_evaluation": 0,
}

# Warn this many days before a document expires.
EXPIRY_WARNING_DAYS = 90

STATUSES = ("missing", "in_progress", "valid", "expiring_soon", "expired")


@dataclass
class VaultEntry:
    """One document in the student's vault."""

    doc_type: str
    label: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    status: str = "missing"
    institution_or_issuer: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "label": self.label,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None,
            "status": self.status,
            "institution_or_issuer": self.institution_or_issuer,
            "notes": self.notes,
        }


@dataclass
class VaultWarning:
    """A warning about a document relative to an application deadline."""

    doc_type: str
    severity: str
    message: str
    expires_on: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "severity": self.severity,
            "message": self.message,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None,
        }


def compute_status(
    entry: VaultEntry,
    *,
    deadline: date | None = None,
    today: date | None = None,
) -> VaultEntry:
    """Update the status of a document relative to an application deadline."""
    reference = today or date.today()
    window = VALIDITY_WINDOW_DAYS.get(entry.doc_type, 0)

    if entry.status in ("missing", "in_progress"):
        return entry

    if entry.expires_on is None:
        entry.status = "valid"
        return entry

    if deadline is not None and window > 0:
        # Only documents with an explicit validity window (a passport must stay
        # valid for months beyond travel) are checked against the deadline.
        # Language tests are judged by age, not by expiry, so their expiry
        # date never invalidates them for a deadline.
        required_until = deadline + timedelta(days=window)
        if entry.expires_on < required_until:
            entry.status = "expired"
            return entry

    if entry.expires_on < reference:
        entry.status = "expired"
    elif entry.expires_on < reference + timedelta(days=EXPIRY_WARNING_DAYS):
        entry.status = "expiring_soon"
    else:
        entry.status = "valid"
    return entry


def warnings_for(
    entries: Sequence[VaultEntry],
    *,
    deadline: date | None = None,
    today: date | None = None,
) -> list[VaultWarning]:
    """Warnings about documents relative to an application deadline."""
    reference = today or date.today()
    warnings: list[VaultWarning] = []

    for entry in entries:
        updated = compute_status(entry, deadline=deadline, today=reference)
        if updated.status == "expired":
            if updated.expires_on and deadline and updated.expires_on < deadline:
                message = (
                    f"Your {updated.doc_type.replace('_', ' ')} expires before the application "
                    "deadline. Renew it before applying."
                )
            else:
                message = f"Your {updated.doc_type.replace('_', ' ')} has expired."
            warnings.append(VaultWarning(updated.doc_type, "high", message, updated.expires_on))
        elif updated.status == "expiring_soon":
            warnings.append(
                VaultWarning(
                    updated.doc_type,
                    "medium",
                    f"Your {updated.doc_type.replace('_', ' ')} expires on "
                    f"{updated.expires_on.isoformat() if updated.expires_on else 'unknown'}.",
                    updated.expires_on,
                )
            )
        elif updated.status == "missing":
            warnings.append(
                VaultWarning(
                    updated.doc_type,
                    "medium",
                    f"You have not recorded a {updated.doc_type.replace('_', ' ')} yet.",
                )
            )
    return warnings


def vault_status(
    entries: Sequence[VaultEntry],
    *,
    required_doc_types: Sequence[str] = (),
    deadline: date | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """A summary of the vault against the documents a cycle requires."""
    reference = today or date.today()
    updated = [compute_status(entry, deadline=deadline, today=reference) for entry in entries]

    by_type = {entry.doc_type: entry for entry in updated}
    missing: list[str] = []
    for doc_type in required_doc_types:
        entry = by_type.get(doc_type)
        if entry is None or entry.status == "missing":
            missing.append(doc_type)

    return {
        "entries": [entry.to_dict() for entry in updated],
        "warnings": [warning.to_dict() for warning in warnings_for(updated, deadline=deadline, today=reference)],
        "missing_required": missing,
        "complete": not missing,
    }
