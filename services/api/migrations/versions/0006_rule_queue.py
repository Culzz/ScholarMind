"""The rule review queue.

Eligibility rules are never decided by a model. Whether drafted by the LLM
(``drafted_by = 'llm'``) or by the regex extractor (``drafted_by = 'regex'``),
every proposed rule lands here as a candidate with its true character span and
is only promoted into ``eligibility_rules`` - with ``authored_by = 'human'`` -
when a reviewer approves it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_rule_queue"
down_revision = "0005_foundation"
branch_labels = None
depends_on = None

CANDIDATE_STATUSES = ("proposed", "approved", "rejected")


def upgrade() -> None:
    op.create_table(
        "rule_candidates",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "cycle_id",
            sa.UUID(),
            sa.ForeignKey("scholarship_cycles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.UUID(),
            sa.ForeignKey("source_snapshots.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "chunk_id",
            sa.UUID(),
            sa.ForeignKey("evidence_chunks.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("operator", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="null"),
        sa.Column("comparator", sa.Text(), nullable=False, server_default="mandatory"),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("span_text", sa.Text(), nullable=False),
        sa.Column("doc_url", sa.Text()),
        sa.Column("drafted_by", sa.Text(), nullable=False, server_default="regex"),
        sa.Column("model_id", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("validation_notes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reviewer_id", sa.UUID()),
        sa.Column("reviewer_note", sa.Text()),
        sa.Column("approved_rule_id", sa.UUID()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name="ck_rule_candidates_status"),
        sa.CheckConstraint("drafted_by IN ('llm', 'regex')", name="ck_rule_candidates_drafted_by"),
        sa.CheckConstraint("comparator IN ('mandatory', 'optional')", name="ck_rule_candidates_comparator"),
        sa.CheckConstraint("span_end > span_start AND span_start >= 0", name="ck_rule_candidates_span"),
        sa.UniqueConstraint("cycle_id", "kind", "subject", "operator", "span_start", "span_end", name="uq_rule_candidates_claim"),
    )
    op.create_index("ix_rule_candidates_status", "rule_candidates", ["status"])
    op.create_index("ix_rule_candidates_cycle_id", "rule_candidates", ["cycle_id"])
    op.create_index("ix_rule_candidates_cycle_kind", "rule_candidates", ["cycle_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_rule_candidates_cycle_kind", table_name="rule_candidates")
    op.drop_index("ix_rule_candidates_cycle_id", table_name="rule_candidates")
    op.drop_index("ix_rule_candidates_status", table_name="rule_candidates")
    op.drop_table("rule_candidates")
