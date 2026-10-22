"""Add the stored full-text vector column to evidence_chunks.

The lexical index was originally created as an expression index over
``to_tsvector('english', content)``. A stored generated column is used instead
so the ranking function can be applied directly to the column, which is what
the retrieval service queries.

This migration is written to be a no-op on a database created from the current
``0001_core`` revision, and to repair one created from the earlier revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_evidence_tsv"
down_revision = "0003_partii"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The index name is reused, so it is dropped first: on a database created
    # from the current 0001 it already points at the stored column, and on an
    # older one it still points at the expression.
    op.execute("DROP INDEX IF EXISTS ix_evidence_chunks_tsv")
    op.execute(
        """
        ALTER TABLE evidence_chunks
        ADD COLUMN IF NOT EXISTS tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_evidence_chunks_tsv ON evidence_chunks USING gin (tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evidence_chunks_tsv")
    op.execute("ALTER TABLE evidence_chunks DROP COLUMN IF EXISTS tsv")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_chunks_tsv ON evidence_chunks "
        "USING gin (to_tsvector('english', content))"
    )
