"""Part II tables: smart questions, unlock paths, grade mapping, waivers,
document vault, selection criteria, readiness evidence, community corrections,
judge calibration and CI thresholds.

Revision ID: 0003_partii
Revises: 0002_platform
Create Date: 2026-10-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_partii"
down_revision = "0002_platform"
branch_labels = None
depends_on = None

UUID = sa.dialects.postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "profile_questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("resolves_unknown_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("affected_rule_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_cycle_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("priority_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("status", sa.Text, nullable=False, server_default="asked"),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_profile_questions_user_id", "profile_questions", ["user_id"])

    op.create_table(
        "unlock_paths",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("profile_change_subject", sa.Text, nullable=False),
        sa.Column("profile_change_from", postgresql.JSONB),
        sa.Column("profile_change_to", postgresql.JSONB, nullable=False),
        sa.Column("unlocked_cycle_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("unlocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("effort_note", sa.Text),
        sa.Column("rule_ids_affected", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("engine_version", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_unlock_paths_user_id", "unlock_paths", ["user_id"])

    op.create_table(
        "grade_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cycle_id", UUID, nullable=False),
        sa.Column("requirement_rule_id", UUID),
        sa.Column("source_scale", sa.Text, nullable=False),
        sa.Column("source_min_value", sa.Text),
        sa.Column("target_scale", sa.Text, nullable=False),
        sa.Column("target_min_value", sa.Numeric(8, 3)),
        sa.Column("equivalence_rule", sa.Text),
        sa.Column("is_exact_match", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_snapshot_id", UUID),
        sa.Column("validation_status", sa.Text, nullable=False, server_default="ambiguous"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_rule_id"], ["eligibility_rules.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_grade_mappings_cycle_id", "grade_mappings", ["cycle_id"])

    op.create_table(
        "waiver_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cycle_id", UUID, nullable=False),
        sa.Column("waiver_kind", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("conditions", sa.Text),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_snapshot_id", UUID),
        sa.Column("validation_status", sa.Text, nullable=False, server_default="ambiguous"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_waiver_rules_cycle_id", "waiver_rules", ["cycle_id"])

    op.create_table(
        "document_vault_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("doc_type", sa.Text, nullable=False),
        sa.Column("label", sa.Text),
        sa.Column("issued_on", sa.Date),
        sa.Column("expires_on", sa.Date),
        sa.Column("status", sa.Text, nullable=False, server_default="missing"),
        sa.Column("institution_or_issuer", sa.Text),
        sa.Column("file_reference", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_vault_entries_user_id", "document_vault_entries", ["user_id"])

    op.create_table(
        "selection_criteria",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cycle_id", UUID, nullable=False),
        sa.Column("criterion_text", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False, server_default="academic"),
        sa.Column("is_mandatory", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("weight", sa.Numeric(4, 3)),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_snapshot_id", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_selection_criteria_cycle_id", "selection_criteria", ["cycle_id"])

    op.create_table(
        "readiness_evidence",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("selection_criterion_id", UUID),
        sa.Column("evidence_text", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False, server_default="user_entry"),
        # The system never fabricates achievements: this flag is always TRUE.
        sa.Column("is_user_supplied", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selection_criterion_id"], ["selection_criteria.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_readiness_evidence_user_id", "readiness_evidence", ["user_id"])

    op.create_table(
        "community_corrections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("reporter_user_id", UUID, nullable=False),
        sa.Column("scholarship_id", UUID),
        sa.Column("cycle_id", UUID),
        sa.Column("field_name", sa.Text, nullable=False),
        sa.Column("claimed_value", postgresql.JSONB),
        sa.Column("note", sa.Text),
        sa.Column("reporter_reputation", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="submitted"),
        sa.Column("verified_by", UUID),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scholarship_id"], ["scholarships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_community_corrections_status", "community_corrections", ["status"])

    op.create_table(
        "evaluation_judgments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("answer_audit_id", UUID, nullable=False),
        sa.Column("claim_index", sa.Integer, nullable=False),
        sa.Column("human_label", sa.Text, nullable=False),
        sa.Column("judge_label", sa.Text),
        sa.Column("agreement", sa.Boolean),
        sa.Column("annotator_id", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["answer_audit_id"], ["answer_audits.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_judgments_answer_audit_id", "evaluation_judgments", ["answer_audit_id"])

    op.create_table(
        "extraction_audit_samples",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("evidence_claim_id", UUID, nullable=False),
        sa.Column("fact_type", sa.Text, nullable=False),
        sa.Column("is_correct", sa.Boolean),
        sa.Column("annotator_id", UUID),
        sa.Column("annotator_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["evidence_claim_id"], ["evidence_claims.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_extraction_audit_samples_fact_type", "extraction_audit_samples", ["fact_type"])

    op.create_table(
        "ci_thresholds",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("metric_key", sa.Text, nullable=False, unique=True),
        sa.Column("metric_value", sa.Numeric(12, 6), nullable=False),
        sa.Column("comparison", sa.Text, nullable=False, server_default="gte"),
        sa.Column("experiment_id", sa.Text),
        sa.Column("dataset_version", sa.Text),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "ci_thresholds",
        "extraction_audit_samples",
        "evaluation_judgments",
        "community_corrections",
        "readiness_evidence",
        "selection_criteria",
        "document_vault_entries",
        "waiver_rules",
        "grade_mappings",
        "unlock_paths",
        "profile_questions",
    ):
        op.drop_table(table)
