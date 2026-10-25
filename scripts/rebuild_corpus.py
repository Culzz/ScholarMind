"""Rebuild the corpus from the capture directory.

Re-running the builder alone is safe but not *clean*: it upserts scholarships
and snapshots, so awards that no longer exist (a programme that used to be split
across six pages) stay in the database. A rebuild therefore removes the
corpus-derived rows first, then imports the current capture.

This deletes scholarship-linked student rows (saved awards, applications,
eligibility assessments, alerts) with the rest of the corpus. It is a
development/demo operation, not a production migration, so it refuses to run
without ``--yes`` and prints what it will remove.

Usage
-----
    PYTHONPATH=".;services/api" python scripts/rebuild_corpus.py --yes
    PYTHONPATH=".;services/api" python scripts/rebuild_corpus.py --yes \
        --captures data/raw/captures
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.services.corpus_builder import DEFAULT_CAPTURES, build_corpus  # noqa: E402

# Children before parents. Order matters: a delete that leaves a referencing
# row behind fails loudly instead of silently truncating half the schema.
CORPUS_TABLES = (
    "alert_deliveries",
    "alerts",
    "application_tasks",
    "readiness_evidence",
    "applications",
    "saved_scholarships",
    "eligibility_assessments",
    "unlock_paths",
    "change_events",
    "scam_signals",
    "conflicts",
    "community_corrections",
    "extraction_audit_samples",
    "eligibility_rules",
    "selection_criteria",
    "waiver_rules",
    "required_documents",
    "funding_components",
    "cycle_predictions",
    "scholarship_cycles",
    "evidence_claims",
    "evidence_chunks",
    "source_snapshots",
    "ingestion_jobs",
    "scholarships",
    "source_documents",
)


def clear_corpus(engine) -> dict[str, int]:
    removed: dict[str, int] = {}
    with engine.begin() as connection:
        for table in CORPUS_TABLES:
            result = connection.execute(text(f"DELETE FROM {table}"))
            removed[table] = result.rowcount or 0
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--captures",
        default=str(DEFAULT_CAPTURES),
        help="directory containing capture_report.json and the captured pages",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm that corpus and scholarship-linked student rows will be deleted",
    )
    args = parser.parse_args(argv)

    if not args.yes:
        print(
            "refusing to run: this deletes the corpus and every scholarship-linked "
            "student row (saved awards, applications, eligibility checks, alerts). "
            "Re-run with --yes to confirm.",
            file=sys.stderr,
        )
        return 2

    engine = get_engine()
    removed = clear_corpus(engine)
    print("removed: " + ", ".join(f"{table}={count}" for table, count in removed.items() if count))

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        stats = build_corpus(session=session, captures_dir=Path(args.captures))
    print(f"built: {stats}")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
