"""Post-rebuild count ledger."""
from sqlalchemy import text

from app.db.session import get_engine

QUERIES = [
    ("scholarships", "SELECT count(*) FROM scholarships"),
    ("source_documents", "SELECT count(*) FROM source_documents"),
    ("scholarship_cycles", "SELECT count(*) FROM scholarship_cycles"),
    (
        "current cycles with deadline",
        "SELECT count(*) FROM scholarship_cycles WHERE is_current AND deadline_at IS NOT NULL",
    ),
    ("snapshots", "SELECT count(*) FROM source_snapshots"),
    ("chunks", "SELECT count(*) FROM evidence_chunks"),
    ("claims", "SELECT count(*) FROM evidence_claims"),
    ("funding", "SELECT count(*) FROM funding_components"),
    ("documents", "SELECT count(*) FROM required_documents"),
    (
        "sd rows claiming ok without a snapshot",
        "SELECT count(*) FROM source_documents d WHERE d.fetch_status = 'ok' "
        "AND NOT EXISTS (SELECT 1 FROM source_snapshots s WHERE s.source_document_id = d.id)",
    ),
]

with get_engine().connect() as conn:
    for name, sql in QUERIES:
        print(name, "=", conn.execute(text(sql)).scalar_one())
