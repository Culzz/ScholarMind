"""Smoke test against a live database.

Run with the corpus loaded:

    DATABASE_URL=postgresql+psycopg://... python scripts/smoke_retrieval.py

It exercises the real retrieval path (Postgres full-text search over the
stored tsvector column) and prints what the system actually returns for
representative queries. It is a manual check, not a unit test.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.db.session import get_engine  # noqa: E402
from app.services.retrieval import retrieve  # noqa: E402

QUERIES = [
    "application deadline",
    "IELTS score requirement",
    "tuition fees and stipend",
    "proof of passport and transcript",
    "work experience requirement",
]


def main() -> int:
    engine = get_engine()
    with engine.connect() as session:
        total = session.execute(
            __import__("sqlalchemy").text("SELECT count(*) FROM evidence_chunks")
        ).scalar_one()
        print(f"indexed chunks: {total}\n")

        for query in QUERIES:
            result = retrieve(session, query, mode="lexical", top_k=3, candidates=50)
            print(f"Q: {query} -> {len(result.chunks)} hits")
            for chunk in result.chunks:
                snippet = " ".join(chunk.content.split())[:110]
                print(f"   [{chunk.rank}] {chunk.source_title or chunk.source_url}")
                print(f"       {snippet}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
