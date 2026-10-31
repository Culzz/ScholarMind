"""Corpus-builder honesty: a failed capture never becomes a record.

These tests need a database (CI provides one; locally set ``DATABASE_URL``).
They are skipped when Postgres is unreachable so the unit suite can run
anywhere. Rows created here carry a unique marker and are removed afterwards.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import text

from app.db.session import get_engine


def _database_available() -> bool:
    if not os.getenv("DATABASE_URL"):
        return False
    try:
        from app.db.session import get_engine

        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="needs a reachable PostgreSQL database"
)


def test_failed_capture_creates_no_records(tmp_path) -> None:
    from app.services.corpus_builder import build_corpus

    marker = f"phantom-{uuid.uuid4().hex[:8]}"
    url = f"https://scam-{marker}.invalid/scholarship"
    name = f"Phantom {marker}"

    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / "capture_report.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "url": url,
                        "name": name,
                        "trust_tier": "official_primary",
                        "ok": False,
                        "status_code": 403,
                        "error": "403 Forbidden",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "\n".join(
            [
                "version: 2",
                f"corpus: test-{marker}",
                "target_intake_year: 2027",
                "sources:",
                f"  - url: {url}",
                f"    name: {name}",
                "    provider_type: university",
                "    trust_tier: official_primary",
            ]
        ),
        encoding="utf-8",
    )

    try:
        from app.db.session import get_session_factory

        session = get_session_factory()()
        try:
            stats = build_corpus(
                session=session, manifest_path=manifest, captures_dir=captures
            )
            # A refused page is warned about, never recorded.
            assert any(marker in warning for warning in stats.warnings)
        finally:
            session.close()

        with get_engine().begin() as connection:
            scholarships = connection.execute(
                text(
                    "SELECT count(*) FROM scholarships WHERE name = :name OR "
                    "provider_name LIKE :postfix"
                ),
                {"name": name, "postfix": f"%{marker}%"},
            ).scalar_one()
            sources = connection.execute(
                text("SELECT count(*) FROM source_documents WHERE url = :url"),
                {"url": url},
            ).scalar_one()
        assert scholarships == 0, "a failed capture fabricated a scholarship record"
        assert sources == 0, "a failed capture fabricated a source document claiming 'ok'"
    finally:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM scholarships WHERE name = :name OR provider_name LIKE :postfix"
                ),
                {"name": name, "postfix": f"%{marker}%"},
            )
            connection.execute(
                text("DELETE FROM source_documents WHERE url = :url"),
                {"url": url},
            )
