"""Users, profiles, applications, alerts and audit tables.

Revision ID: 0002_platform
Revises: 0001_core
Create Date: 2026-10-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_platform"
down_revision = "0001_core"
branch_labels = None
depends_on = None

UUID = sa.dialects.postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.dialects.postgresql.CITEXT, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.Text),
        sa.Column("role", sa.Text, nullable=False, server_default="student"),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("country_iso3", sa.CHAR(3)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "student_profiles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False, unique=True),
        sa.Column("nationality_country_iso3", sa.CHAR(3)),
        sa.Column("residency_country_iso3", sa.CHAR(3)),
        sa.Column("current_degree_level", sa.Text),
        sa.Column("current_institution", sa.Text),
        sa.Column("degree_completion_year", sa.Integer),
        sa.Column("fields_of_study", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("gpa_value", sa.Numeric(6, 3)),
        sa.Column("gpa_scale", sa.Text),
        sa.Column("grade_scale_raw", sa.Text),
        sa.Column("age", sa.Integer),
        sa.Column("work_experience_months", sa.Integer),
        sa.Column("languages", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("preferred_destinations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("preferred_study_modes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("funding_requirements", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("target_intake_year", sa.Integer, nullable=False, server_default="2027"),
        sa.Column("completeness", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "saved_scholarships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("scholarship_id", UUID, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "scholarship_id", name="uq_saved_scholarships_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scholarship_id"], ["scholarships.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "applications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("scholarship_id", UUID, nullable=False),
        sa.Column("cycle_id", UUID, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="planning"),
        sa.Column("target_deadline", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "cycle_id", name="uq_applications_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "application_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("application_id", UUID, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("task_type", sa.Text, nullable=False, server_default="document"),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False, server_default="todo"),
        sa.Column("depends_on_task_id", UUID),
        sa.Column("doc_type", sa.Text),
        sa.Column("is_auto_generated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["application_tasks.id"]),
    )
    op.create_index("ix_application_tasks_application_id", "application_tasks", ["application_id"])

    op.create_table(
        "alerts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("scholarship_id", UUID),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False, server_default="in_app"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scholarship_id"], ["scholarships.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])

    op.create_table(
        "alert_deliveries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("alert_id", UUID, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("event_id", UUID),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("error", sa.Text),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alert_deliveries_alert_id", "alert_deliveries", ["alert_id"])

    op.create_table(
        "eligibility_assessments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("cycle_id", UUID, nullable=False),
        sa.Column("engine_version", sa.Text, nullable=False),
        sa.Column("ruleset_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("profile_hash", sa.Text, nullable=False),
        sa.Column("overall_status", sa.Text, nullable=False),
        sa.Column("verdict_counts", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("results", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["scholarship_cycles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_eligibility_assessments_user_id", "eligibility_assessments", ["user_id"])

    op.create_table(
        "answer_audits",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("question_type", sa.Text),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("retrieval_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("answer_claims", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("citation_map", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("validation_result", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("abstained", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("model_id", sa.Text),
        sa.Column("prompt_version", sa.Text),
        sa.Column("embedding_model", sa.Text),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_answer_audits_user_id", "answer_audits", ["user_id"])
    op.create_index("ix_answer_audits_created_at", "answer_audits", ["created_at"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source_document_id", UUID, nullable=False),
        sa.Column("task_id", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("experiment_id", sa.Text, nullable=False),
        sa.Column("dataset_version", sa.Text, nullable=False),
        sa.Column("split", sa.Text, nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("model_id", sa.Text),
        sa.Column("code_commit", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_evaluation_runs_experiment_id", "evaluation_runs", ["experiment_id"])

    op.create_table(
        "evaluation_items",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("question_type", sa.Text, nullable=False),
        sa.Column("split", sa.Text, nullable=False),
        sa.Column("difficulty", sa.Integer, nullable=False, server_default="1"),
        sa.Column("scholarship_slug", sa.Text),
        sa.Column("required_evidence", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("gold_answer", sa.Text),
        sa.Column("acceptable_abstain", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_evaluation_items_split", "evaluation_items", ["split"])


def downgrade() -> None:
    for table in (
        "evaluation_items",
        "evaluation_runs",
        "ingestion_jobs",
        "answer_audits",
        "eligibility_assessments",
        "alert_deliveries",
        "alerts",
        "application_tasks",
        "applications",
        "saved_scholarships",
        "student_profiles",
        "users",
    ):
        op.drop_table(table)
