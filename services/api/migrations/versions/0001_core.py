"""Core scholarship, cycle, rule and provenance schema.

Revision ID: 0001_core
Revises:
Create Date: 2026-10-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # --- vocabulary -------------------------------------------------------
    op.create_table(
        "countries",
        sa.Column("iso3", sa.CHAR(3), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("region", sa.Text, nullable=False, server_default="africa"),
        sa.Column("is_in_scope", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "fields_of_study",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("parent_code", sa.Text),
        sa.Column("aliases", sa.JSONB, nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["parent_code"], ["fields_of_study.code"]),
    )
    op.create_table(
        "degree_levels",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False, server_default="0"),
    )

    # --- provenance --------------------------------------------------------
    op.create_table(
        "source_documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scholarship_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("trust_tier", sa.Text, nullable=False),
        sa.Column("country_iso3", sa.CHAR(3)),
        sa.Column("refresh_cadence_hours", sa.Integer, nullable=False, server_default="168"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("fetch_status", sa.Text, nullable=False, server_default="ok"),
        sa.Column("fetch_error", sa.Text),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("robots_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_documents_scholarship_id", "source_documents", ["scholarship_id"])
    op.create_index("ix_source_documents_last_checked_at", "source_documents", ["last_checked_at"])

    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("raw_content", sa.LargeBinary),
        sa.Column("extracted_text", sa.Text),
        sa.Column("http_status", sa.Integer),
        sa.Column("headers", sa.JSONB, nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("extraction_version", sa.Text),
        sa.Column("fetched_by", sa.Text, nullable=False, server_default="scheduler"),
        sa.UniqueConstraint("source_document_id", "content_hash", name="uq_source_snapshots_source_document_id"),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
    )
    op.create_index("ix_source_snapshots_source_document_id", "source_snapshots", ["source_document_id"])
    op.create_index("ix_source_snapshots_fetched_at", "source_snapshots", ["fetched_at"])

    # --- scholarship core --------------------------------------------------
    op.create_table(
        "scholarships",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("provider_type", sa.Text, nullable=False),
        sa.Column("provider_name", sa.Text),
        sa.Column("provider_country_iso3", sa.CHAR(3)),
        sa.Column("description", sa.Text),
        sa.Column("study_levels", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("fields_of_study", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("destinations", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("canonical_source_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trust_tier", sa.Text, nullable=False, server_default="official_primary"),
        sa.Column("website_url", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["canonical_source_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["provider_country_iso3"], ["countries.iso3"]),
    )
    op.create_index("ix_scholarships_status", "scholarships", ["status"])
    op.create_index("ix_scholarships_provider_type", "scholarships", ["provider_type"])

    op.create_table(
        "scholarship_cycles",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scholarship_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intake_year", sa.Integer, nullable=False),
        sa.Column("cycle_label", sa.Text),
        sa.Column("opens_at", sa.Date),
        sa.Column("opens_at_precision", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_timezone", sa.Text),
        sa.Column("deadline_raw_text", sa.Text),
        sa.Column("deadline_precision", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("status", sa.Text, nullable=False, server_default="undetermined"),
        sa.Column("status_confidence", sa.Text, nullable=False, server_default="confirmed"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scholarship_id", "intake_year", name="uq_scholarship_cycles_scholarship_id"),
        sa.ForeignKeyConstraint(["scholarship_id"], ["scholarships.id"]),
    )
    op.create_index("ix_scholarship_cycles_deadline_at", "scholarship_cycles", ["deadline_at"])
    op.create_index("ix_scholarship_cycles_status", "scholarship_cycles", ["status"])

    op.create_table(
        "eligibility_rules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("operator", sa.Text, nullable=False),
        sa.Column("value", sa.JSONB, nullable=False),
        sa.Column("comparator", sa.Text, nullable=False, server_default="mandatory"),
        sa.Column("rule_text", sa.Text, nullable=False),
        sa.Column("evidence_ids", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_snapshot_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("ambiguity_flag", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("authored_by", sa.Text, nullable=False, server_default="human"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"]),
    )
    op.create_index("ix_eligibility_rules_cycle_id", "eligibility_rules", ["cycle_id"])

    op.create_table(
        "funding_components",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component", sa.Text, nullable=False),
        sa.Column("coverage_status", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("currency", sa.CHAR(3)),
        sa.Column("amount_period", sa.Text),
        sa.Column("conditions", sa.Text),
        sa.Column("evidence_ids", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_snapshot_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"]),
    )
    op.create_index("ix_funding_components_cycle_id", "funding_components", ["cycle_id"])

    op.create_table(
        "required_documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.Text, nullable=False),
        sa.Column("is_mandatory", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text),
        sa.Column("lead_time_days", sa.Integer),
        sa.Column("evidence_ids", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("country_scope", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("requires_notarization", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requires_apostille", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requires_credential_evaluation", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("lead_time_days_default", sa.Integer),
        sa.Column("issue_window_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"]),
    )
    op.create_index("ix_required_documents_cycle_id", "required_documents", ["cycle_id"])

    # --- evidence ----------------------------------------------------------
    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_path", sa.Text),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536)),
        sa.Column("embedding_model", sa.Text),
        sa.Column("token_count", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshots.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
    )
    op.execute(
        "CREATE INDEX ix_evidence_chunks_tsv ON evidence_chunks "
        "USING gin (to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX ix_evidence_chunks_embedding ON evidence_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_index("ix_evidence_chunks_source_document_id", "evidence_chunks", ["source_document_id"])

    op.create_table(
        "evidence_claims",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("span_start", sa.Integer, nullable=False),
        sa.Column("span_end", sa.Integer, nullable=False),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("claim_type", sa.Text, nullable=False),
        sa.Column("subject_entity", sa.Text),
        sa.Column("subject_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("field_name", sa.Text),
        sa.Column("normalized_value", sa.JSONB),
        sa.Column("validation_status", sa.Text, nullable=False, server_default="ambiguous"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("extraction_method", sa.Text, nullable=False, server_default="llm"),
        sa.Column("reviewed_by", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshots.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["evidence_chunks.id"]),
    )
    op.create_index("ix_evidence_claims_snapshot_id", "evidence_claims", ["snapshot_id"])
    op.create_index("ix_evidence_claims_validation_status", "evidence_claims", ["validation_status"])

    # --- change tracking ---------------------------------------------------
    op.create_table(
        "change_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prev_snapshot_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("new_snapshot_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("cycle_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("field_name", sa.Text, nullable=False),
        sa.Column("old_value", sa.JSONB),
        sa.Column("new_value", sa.JSONB),
        sa.Column("change_type", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False, server_default="informational"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("review_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_note", sa.Text),
        sa.Column("auto_accept_confidence", sa.Float),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"]),
    )
    op.create_index("ix_change_events_review_status", "change_events", ["review_status"])
    op.create_index("ix_change_events_detected_at", "change_events", ["detected_at"])

    op.create_table(
        "conflicts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.Text, nullable=False),
        sa.Column("value_a", sa.JSONB),
        sa.Column("value_b", sa.JSONB),
        sa.Column("evidence_id_a", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_id_b", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("source_document_id_a", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("source_document_id_b", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("resolution_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conflicts_status", "conflicts", ["status"])

    op.create_table(
        "scam_signals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False, server_default="medium"),
        sa.Column("detail", sa.Text),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("detection_method", sa.Text, nullable=False, server_default="rule"),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
    )
    op.create_index("ix_scam_signals_source_document_id", "scam_signals", ["source_document_id"])

    op.create_table(
        "cycle_predictions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scholarship_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("predicted_intake_year", sa.Integer, nullable=False),
        sa.Column("predicted_open_date", sa.Date),
        sa.Column("predicted_close_date", sa.Date),
        sa.Column("method", sa.Text, nullable=False, server_default="median_day_of_year"),
        sa.Column("confidence", sa.Text, nullable=False, server_default="low"),
        sa.Column("supporting_snapshot_ids", sa.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_estimate", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["scholarship_id"], ["scholarships.id"]),
    )
    # Predictions are estimates only: they must never be indexed together with
    # confirmed cycle deadlines used by the "currently open" filter.
    op.create_index("ix_cycle_predictions_scholarship_id", "cycle_predictions", ["scholarship_id"])


def downgrade() -> None:
    for table in (
        "cycle_predictions",
        "scam_signals",
        "conflicts",
        "change_events",
        "evidence_claims",
        "evidence_chunks",
        "required_documents",
        "funding_components",
        "eligibility_rules",
        "scholarship_cycles",
        "scholarships",
        "source_snapshots",
        "source_documents",
        "degree_levels",
        "fields_of_study",
        "countries",
    ):
        op.drop_table(table)
    op.execute("DROP EXTENSION IF EXISTS citext")
