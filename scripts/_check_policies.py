"""Check which bot-blocked / manual-review sources have DB rows."""
from sqlalchemy import text
from app.db.session import get_engine

URLS = [
    "https://nddc.gov.ng/",
    "https://fulbrightprogram.org/",
    "https://www.ox.ac.uk/clarendon",
    "https://www.cam.ac.uk/finance/funding",
    "https://www.ed.ac.uk/student-funding/postgraduate/research",
    "https://www.setd.gov.ng/",
    "https://www.aku.edu.ng/",
    "https://www.unilag.edu.ng/",
    "https://www.commonwealthscholarships.org/",
]
with get_engine().connect() as conn:
    rows = conn.execute(
        text(
            "SELECT d.url, d.fetch_status, "
            "count(s.id) AS snapshots, "
            "count(c.id) AS chunks "
            "FROM source_documents d "
            "LEFT JOIN source_snapshots s ON s.source_document_id = d.id "
            "LEFT JOIN evidence_chunks c ON c.source_document_id = d.id "
            "WHERE d.url = ANY(:urls) "
            "GROUP BY d.url, d.fetch_status"
        ),
        {"urls": URLS},
    ).fetchall()
print(len(rows), "present in DB")
for r in rows:
    print(r)
