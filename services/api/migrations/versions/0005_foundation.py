"""Refresh-token families, freshness state and insert idempotency.

Three fixes share one migration because they are the Phase 1 foundation:

* refresh tokens are stored server-side so rotation can be enforced and a
  reused token can revoke its whole family;
* source freshness gets its own state instead of being smuggled into the
  trust tier or derived from ``last_success_at`` alone;
* chunks and claims get unique keys, so rerunning an extraction task cannot
  duplicate evidence.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_foundation"
down_revision = "0004_evidence_tsv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by", sa.UUID()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("ip_address", sa.Text()),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.add_column("source_documents", sa.Column("last_attempt_at", sa.DateTime(timezone=True)))
    op.add_column(
        "source_documents",
        sa.Column("freshness_state", sa.Text(), nullable=False, server_default="unknown"),
    )
    op.execute(
        "UPDATE source_documents SET last_attempt_at = coalesce(last_checked_at, last_success_at)"
    )
    op.execute(
        """
        UPDATE source_documents
        SET freshness_state = CASE
            WHEN fetch_status = 'stale' THEN 'stale'
            WHEN last_success_at IS NULL THEN 'unknown'
            ELSE 'fresh'
        END
        """
    )

    # Existing rows may already contain duplicates from a rebuild; keep the
    # earliest of each group before adding the keys.
    op.execute(
        """
        DELETE FROM evidence_chunks c
        USING evidence_chunks d
        WHERE c.snapshot_id = d.snapshot_id
          AND c.content_hash = d.content_hash
          AND c.id > d.id
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_chunks_snapshot_content "
        "ON evidence_chunks (snapshot_id, content_hash)"
    )

    op.execute(
        """
        DELETE FROM evidence_claims c
        USING evidence_claims d
        WHERE c.snapshot_id = d.snapshot_id
          AND c.claim_type = d.claim_type
          AND c.span_start = d.span_start
          AND c.span_end = d.span_end
          AND c.id > d.id
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_claims_snapshot_span "
        "ON evidence_claims (snapshot_id, claim_type, span_start, span_end)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_evidence_claims_snapshot_span")
    op.execute("DROP INDEX IF EXISTS uq_evidence_chunks_snapshot_content")
    op.drop_column("source_documents", "freshness_state")
    op.drop_column("source_documents", "last_attempt_at")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
