"""Tests for the readiness studio and the document vault."""

from __future__ import annotations

from datetime import date

from scholarmind.readiness.studio import (
    SelectionCriterion,
    UserEvidence,
    assess_readiness,
)
from scholarmind.vault.documents import VaultEntry, compute_status, vault_status, warnings_for


def test_readiness_maps_evidence_onto_criteria() -> None:
    criteria = [
        SelectionCriterion("c1", "Student leadership in a society or committee", "personal"),
        SelectionCriterion("c2", "A first class degree in engineering", "academic"),
    ]
    evidence = [
        UserEvidence("e1", "Student leader of the robotics society; led a committee of twelve members"),
    ]
    report = assess_readiness(scholarship_id="s1", criteria=criteria, evidence=evidence)

    mappings = {mapping.criterion.criterion_id: mapping for mapping in report.mappings}
    assert mappings["c1"].status in ("covered", "partial")
    assert mappings["c2"].status == "gap"
    assert report.gaps == ["A first class degree in engineering"]


def test_readiness_never_uses_non_user_supplied_evidence() -> None:
    criteria = [SelectionCriterion("c1", "Research publication in the field", "research")]
    evidence = [UserEvidence("e1", "Published a paper on malaria genomics", is_user_supplied=False)]
    report = assess_readiness(scholarship_id="s1", criteria=criteria, evidence=evidence)
    assert report.mappings[0].status == "gap"
    assert report.mappings[0].matched_evidence == []


def test_readiness_report_states_the_no_fabrication_rule() -> None:
    report = assess_readiness(
        scholarship_id="s1",
        criteria=[SelectionCriterion("c1", "Leadership")],
        evidence=[UserEvidence("e1", "Led a project")],
    )
    payload = report.to_dict()
    assert "was written" in payload["no_fabrication_note"]
    assert "not a selection prediction" in payload["readiness_interpretation"]


def test_readiness_lists_unused_evidence() -> None:
    report = assess_readiness(
        scholarship_id="s1",
        criteria=[SelectionCriterion("c1", "Leadership in community service")],
        evidence=[UserEvidence("e1", "Cleaned data for a marketing agency")],
    )
    assert "e1" in report.unused_evidence


def test_document_status_depends_on_the_deadline() -> None:
    entry = VaultEntry(doc_type="passport", expires_on=date(2027, 1, 1), status="valid")
    updated = compute_status(entry, deadline=date(2027, 3, 15), today=date(2026, 10, 20))
    assert updated.status == "expired"


def test_document_status_expiring_soon() -> None:
    entry = VaultEntry(doc_type="ielts", expires_on=date(2026, 12, 1), status="valid")
    updated = compute_status(entry, deadline=date(2027, 3, 15), today=date(2026, 10, 20))
    assert updated.status == "expiring_soon"


def test_document_without_expiry_is_valid() -> None:
    entry = VaultEntry(doc_type="transcript", status="valid")
    assert compute_status(entry, today=date(2026, 10, 20)).status == "valid"


def test_vault_reports_missing_required_documents() -> None:
    entries = [VaultEntry(doc_type="passport", expires_on=date(2029, 1, 1), status="valid")]
    status = vault_status(
        entries,
        required_doc_types=["passport", "transcript", "lor"],
        deadline=date(2027, 3, 15),
        today=date(2026, 10, 20),
    )
    assert status["missing_required"] == ["transcript", "lor"]
    assert status["complete"] is False


def test_vault_warnings_include_missing_documents() -> None:
    warnings = warnings_for(
        [VaultEntry(doc_type="transcript", status="missing")],
        deadline=date(2027, 3, 15),
        today=date(2026, 10, 20),
    )
    assert warnings
    assert warnings[0].severity == "medium"
