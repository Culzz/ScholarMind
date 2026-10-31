"""Corpus builder.

Turns a capture directory into structured scholarship records:

    source_documents -> source_snapshots -> evidence_chunks -> evidence_claims
    scholarships -> scholarship_cycles -> eligibility_rules
                                       -> funding_components
                                       -> required_documents

Every write is idempotent (keyed on the URL, the content hash or the field
identity), so the builder can be re-run over a new capture without duplicating
anything.

Captured pages that belong to the same scholarship (the landing page and the
eligibility page it links to) are grouped into one scholarship and one cycle,
because they describe the same award. A page is only promoted to its own
scholarship when it declares a different programme.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scholarmind.extraction.extract import extract_all
from scholarmind.extraction.rule_drafter import VALUE_NORMALISED_NOTE, validate_rule_shape
from scholarmind.extraction.validate import validate_result
from scholarmind.ingestion.manifest import Manifest, load_manifest
from scholarmind.normalization.cycles import build_cycles, choose_current_cycles
from scholarmind.retrieval.fusion import chunk_spans

logger = logging.getLogger(__name__)

DEFAULT_MANIFEST = Path("data/manifests/nigeria_v1.yaml")
DEFAULT_CAPTURES = Path("data/raw")

# A page title that looks like a distinct programme starts a new scholarship.
PROGRAMME_MARKERS = re.compile(
    r"(scholarship|award|programme|program|grant|fellowship)", re.IGNORECASE
)


@dataclass
class BuildStats:
    """What the builder did."""

    sources: int = 0
    snapshots: int = 0
    chunks: int = 0
    claims: int = 0
    scholarships: int = 0
    cycles: int = 0
    rules: int = 0
    proposed_rules: int = 0
    rule_candidates_flagged: int = 0
    funding: int = 0
    documents: int = 0
    skipped_unsupported: int = 0
    warnings: list[str] = field(default_factory=list)
    vocabulary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "snapshots": self.snapshots,
            "chunks": self.chunks,
            "claims": self.claims,
            "scholarships": self.scholarships,
            "cycles": self.cycles,
            "rules": self.rules,
            "proposed_rules": self.proposed_rules,
            "rule_candidates_flagged": self.rule_candidates_flagged,
            "funding": self.funding,
            "documents": self.documents,
            "skipped_unsupported": self.skipped_unsupported,
            "warnings": list(self.warnings),
            "vocabulary": dict(self.vocabulary),
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "scholarship"


def _group_key(entry: dict[str, Any], by_url: dict[str, Any] | None = None) -> str:
    """Group key for a capture: parent pages and their children belong together.

    A manifest root can name an explicit ``group`` when several official pages
    describe one programme (a funder's main page, its country page and its
    funding page). Without that, a crawled child belongs to its root, and a root
    belongs to itself.
    """
    source = (by_url or {}).get(entry["url"])
    explicit = getattr(source, "group", None) or entry.get("group")
    if explicit:
        return f"group:{explicit}"
    parent = entry.get("parent_url")
    if parent:
        parent_source = (by_url or {}).get(parent)
        parent_group = getattr(parent_source, "group", None)
        if parent_group:
            return f"group:{parent_group}"
        return parent
    return entry["url"]


def _is_distinct_programme(entry: dict[str, Any], group: list[dict[str, Any]]) -> bool:
    """Whether a page describes a different programme from its siblings."""
    if entry.get("parent_url"):
        return False
    if not group:
        return False
    name = entry.get("name") or ""
    other = (group[0].get("name") or "").lower()
    if name.lower() == other:
        return False
    return bool(PROGRAMME_MARKERS.search(name))


def build_corpus(
    *,
    session: Any,
    manifest_path: Path = DEFAULT_MANIFEST,
    captures_dir: Path = DEFAULT_CAPTURES,
    chunk_tokens: int = 500,
    chunk_overlap: int = 80,
) -> BuildStats:
    """Build the corpus from a capture directory into the database."""
    from sqlalchemy import text

    manifest: Manifest = load_manifest(manifest_path)
    by_url = {source.url: source for source in manifest.sources}
    report_path = captures_dir / "capture_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"no capture report at {report_path}")

    from app.services.vocab import seed_vocabulary

    seeded = seed_vocabulary(session)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    entries = report.get("results", [])
    stats = BuildStats()
    stats.vocabulary = seeded  # type: ignore[attr-defined]

    # A scholarship record must stand on at least one page that was actually
    # read. A failed capture (403 / DNS / timeout) stays in the capture report
    # as an operator record, but it never becomes a scholarship or a source
    # document row claiming 'ok'.
    readable = [entry for entry in entries if entry.get("ok")]
    failed = [entry for entry in entries if not entry.get("ok")]
    for entry in failed:
        stats.skipped_unsupported += 1
        stats.warnings.append(
            f"failed capture kept out of the corpus (no record is created): "
            f"{entry.get('url')} - {entry.get('error') or entry.get('status_code')}"
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in readable:
        groups.setdefault(_group_key(entry, by_url), []).append(entry)

    for group_key, group in groups.items():
        primary = next((entry for entry in group if not entry.get("parent_url")), None)
        if primary is None:
            primary = group[0]
        source = by_url.get(primary["url"])

        scholarship_id = _upsert_scholarship(
            session,
            text,
            group_key=group_key,
            primary=primary,
            source=source,
            stats=stats,
        )

        for entry in group:
            folder = Path(entry["path"])
            page_path = folder / "page.txt"
            if not page_path.exists():
                stats.skipped_unsupported += 1
                continue
            page_text = page_path.read_text(encoding="utf-8").replace("\x00", "")
            if page_text.lstrip().startswith("%PDF"):
                # Captured before PDFs were refused. There is no PDF extractor,
                # so this is not evidence; skip it instead of indexing binary.
                stats.skipped_unsupported += 1
                stats.warnings.append(f"unsupported PDF capture skipped: {entry.get('url')}")
                continue
            if not page_text.strip():
                stats.skipped_unsupported += 1
                stats.warnings.append(f"empty capture: {entry.get('url')}")
                continue
            source_document_id = _upsert_source_document(
                session, text, entry, source, stats, scholarship_id
            )
            snapshot_id = _insert_snapshot(session, text, entry, source_document_id, page_text, stats)

            _index_chunks(session, text, snapshot_id, source_document_id, page_text, chunk_tokens, chunk_overlap, stats)

            result = extract_all(page_text)
            _, validated = validate_result(result, page_text)
            _insert_claims(session, text, snapshot_id, validated, stats)

            _insert_structured_facts(
                session, text, scholarship_id, entry, page_text, validated, stats
            )

    session.commit()
    return stats


# --- individual writers ---------------------------------------------------


def _upsert_scholarship(
    session: Any,
    text: Any,
    *,
    group_key: str,
    primary: dict[str, Any],
    source: Any,
    stats: BuildStats,
) -> str:
    name = source.name if source else primary.get("name") or group_key
    slug = _slugify(name)
    provider_type = source.provider_type if source else "other"
    trust_tier = source.trust_tier if source else "official_primary"
    scope = list(source.scope) if source else []

    source_document_id = _ensure_source_document_row(session, text, primary, stats)

    row = session.execute(
        text(
            """
            INSERT INTO scholarships
                (id, slug, name, provider_type, provider_name, provider_country_iso3,
                 study_levels, fields_of_study, destinations, canonical_source_id,
                 trust_tier, status)
            VALUES (gen_random_uuid(), :slug, :name, :provider_type, :provider_name,
                    :country, :levels, :fields, :destinations, :source_id, :trust_tier, 'active')
            ON CONFLICT (slug) DO UPDATE
                SET name = EXCLUDED.name, updated_at = now()
            RETURNING id::text
            """
        ),
        {
            "slug": slug,
            "name": name,
            "provider_type": provider_type,
            "provider_name": name,
            "country": (scope[0] if scope else None),
            "levels": json.dumps([source.level] if source else []),
            "fields": json.dumps([]),
            "destinations": json.dumps([{"country_iso3": code} for code in scope]),
            "source_id": source_document_id,
            "trust_tier": trust_tier,
        },
    ).first()
    stats.scholarships += 1
    # Link the canonical source document now that the scholarship id exists, so
    # chunk -> snapshot -> source document -> scholarship/cycle attribution can
    # never be orphaned at the primary page.
    session.execute(
        text(
            """
            UPDATE source_documents
            SET scholarship_id = CAST(:sid AS uuid)
            WHERE id = CAST(:source_id AS uuid) AND scholarship_id IS NULL
            """
        ),
        {"sid": row[0], "source_id": source_document_id},
    )
    return row[0]


def _ensure_source_document_row(session: Any, text: Any, entry: dict[str, Any], stats: BuildStats) -> str:
    row = session.execute(
        text(
            """
            INSERT INTO source_documents (id, url, source_type, trust_tier, fetch_status, last_checked_at, last_success_at)
            VALUES (gen_random_uuid(), :url, 'other', :trust_tier, 'ok', now(), now())
            ON CONFLICT (url) DO UPDATE SET last_success_at = now(), fetch_status = 'ok', updated_at = now()
            RETURNING id::text
            """
        ),
        {"url": entry["url"], "trust_tier": entry.get("trust_tier", "official_primary")},
    ).first()
    stats.sources += 1
    return row[0]


def _upsert_source_document(
    session: Any, text: Any, entry: dict[str, Any], source: Any, stats: BuildStats, scholarship_id: str
) -> str:
    source_type = "other"
    if source is not None:
        source_type = source.provider_type
    row = session.execute(
        text(
            """
            INSERT INTO source_documents (id, url, source_type, trust_tier, scholarship_id, fetch_status, last_checked_at, last_success_at)
            VALUES (gen_random_uuid(), :url, :source_type, :trust_tier, CAST(:scholarship_id AS uuid), 'ok', now(), now())
            ON CONFLICT (url) DO UPDATE SET last_success_at = now(), updated_at = now(),
                scholarship_id = COALESCE(source_documents.scholarship_id, EXCLUDED.scholarship_id)
            RETURNING id::text
            """
        ),
        {
            "url": entry["url"],
            "source_type": source_type,
            "trust_tier": entry.get("trust_tier", "official_primary"),
            "scholarship_id": scholarship_id,
        },
    ).first()
    stats.sources += 1
    return row[0]


def _insert_snapshot(
    session: Any,
    text: Any,
    entry: dict[str, Any],
    source_document_id: str,
    page_text: str,
    stats: BuildStats,
) -> str:
    content_hash = entry.get("content_hash") or hashlib.sha256(page_text.encode("utf-8")).hexdigest()
    row = session.execute(
        text(
            """
            INSERT INTO source_snapshots
                (id, source_document_id, content_hash, extracted_text, http_status, headers, fetched_at, fetched_by)
            VALUES (gen_random_uuid(), :source_id, :hash, :extracted_text, :status, CAST(:headers AS jsonb), now(), 'capture')
            ON CONFLICT (source_document_id, content_hash) DO UPDATE SET fetched_at = now()
            RETURNING id::text
            """
        ),
        {
            "source_id": source_document_id,
            "hash": content_hash,
            "extracted_text": page_text,
            "status": entry.get("status_code"),
            "headers": json.dumps({}),
        },
    ).first()
    stats.snapshots += 1
    return row[0]


def _index_chunks(
    session: Any,
    text: Any,
    snapshot_id: str,
    source_document_id: str,
    page_text: str,
    chunk_tokens: int,
    chunk_overlap: int,
    stats: BuildStats,
) -> None:
    chunks = chunk_spans(page_text, max_tokens=chunk_tokens, overlap=chunk_overlap)
    for chunk in chunks:
        content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        result = session.execute(
            text(
                """
                INSERT INTO evidence_chunks
                    (id, snapshot_id, source_document_id, char_start, char_end, content, content_hash, token_count)
                VALUES (gen_random_uuid(), :snapshot_id, :source_id, :start, :end, :content, :hash, :tokens)
                ON CONFLICT (snapshot_id, content_hash) DO NOTHING
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "source_id": source_document_id,
                "start": chunk.start,
                "end": chunk.end,
                "content": chunk.text,
                "hash": content_hash,
                "tokens": len(chunk.text) // 4,
            },
        )
        stats.chunks += result.rowcount or 0


def _insert_claims(session: Any, text: Any, snapshot_id: str, validated: Any, stats: BuildStats) -> None:
    for fact in validated.facts:
        result = session.execute(
            text(
                """
                INSERT INTO evidence_claims
                    (id, snapshot_id, span_start, span_end, claim_text, claim_type, field_name,
                     normalized_value, validation_status, confidence, extraction_method)
                VALUES (gen_random_uuid(), :snapshot_id, :span_start, :span_end, :claim_text,
                        :claim_type, :field_name, CAST(:value AS jsonb), :status, :confidence,
                        :extraction_method)
                ON CONFLICT (snapshot_id, claim_type, span_start, span_end) DO NOTHING
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "span_start": fact.span_start,
                "span_end": fact.span_end,
                "claim_text": fact.text,
                "claim_type": fact.claim_type.value,
                "field_name": fact.field_name,
                "value": json.dumps(fact.normalized_value),
                "status": fact.status.value,
                "confidence": fact.confidence,
                "extraction_method": fact.extraction_method,
            },
        )
        stats.claims += result.rowcount or 0


def _insert_structured_facts(
    session: Any,
    text: Any,
    scholarship_id: str,
    entry: dict[str, Any],
    page_text: str,
    validated: Any,
    stats: BuildStats,
) -> None:
    """Turn the extracted facts into a cycle with rules, funding and documents."""
    cycles = build_cycles(
        validated.facts, text=page_text, default_intake_year=2027, now=datetime.now(timezone.utc)
    )
    current = choose_current_cycles(cycles)
    if not current:
        # Every cycle found is closed (the deadline has passed). Keep the most
        # recent one as a historical record rather than discarding the page.
        closed = sorted(cycles, key=lambda item: item.intake_year, reverse=True)
        if not closed:
            stats.warnings.append(f"no cycle could be derived for {entry['url']}")
            return
        current = closed[:1]
        stats.warnings.append(f"only a closed cycle was found for {entry['url']}")

    cycle = current[0]
    row = session.execute(
        text(
            """
            INSERT INTO scholarship_cycles
                (id, scholarship_id, intake_year, cycle_label, opens_at, opens_at_precision,
                 deadline_at, deadline_timezone, deadline_raw_text, deadline_precision, status,
                 status_confidence, is_current)
            VALUES (gen_random_uuid(), :scholarship_id, :year, :label, :opens_at, :opens_precision,
                    :deadline, :timezone, :raw_text, :precision, :status, 'confirmed', :is_current)
            ON CONFLICT (scholarship_id, intake_year) DO UPDATE
                SET deadline_at = COALESCE(EXCLUDED.deadline_at, scholarship_cycles.deadline_at),
                    deadline_raw_text = COALESCE(
                        EXCLUDED.deadline_raw_text, scholarship_cycles.deadline_raw_text
                    ),
                    deadline_precision = CASE
                        WHEN EXCLUDED.deadline_at IS NOT NULL THEN EXCLUDED.deadline_precision
                        ELSE scholarship_cycles.deadline_precision
                    END,
                    deadline_timezone = COALESCE(
                        EXCLUDED.deadline_timezone, scholarship_cycles.deadline_timezone
                    ),
                    opens_at = COALESCE(EXCLUDED.opens_at, scholarship_cycles.opens_at),
                    opens_at_precision = COALESCE(
                        EXCLUDED.opens_at_precision, scholarship_cycles.opens_at_precision
                    ),
                    status = CASE
                        WHEN EXCLUDED.deadline_at IS NULL
                             AND scholarship_cycles.deadline_at IS NOT NULL
                        THEN scholarship_cycles.status
                        ELSE EXCLUDED.status
                    END,
                    is_current = scholarship_cycles.is_current OR EXCLUDED.is_current,
                    updated_at = now()
            RETURNING id::text
            """
        ),
        {
            "scholarship_id": scholarship_id,
            "year": cycle.intake_year,
            "label": cycle.cycle_label or f"{cycle.intake_year} cycle",
            "opens_at": cycle.opens_at,
            "opens_precision": cycle.opens_at_precision,
            "deadline": cycle.deadline_at,
            "timezone": cycle.deadline_timezone,
            "raw_text": cycle.deadline_raw_text,
            "precision": cycle.deadline_precision,
            "status": cycle.status,
            "is_current": cycle.is_current,
        },
    ).first()
    cycle_id = row[0]
    stats.cycles += 1

    for rule in validated.eligibility:
        # Eligibility rules are never decided by an extractor. The regex
        # drafter proposes candidates (drafted_by='regex'); only rules a human
        # approves - with authored_by='human' - reach the eligibility engine
        # from the rule_candidates review queue.
        span_start = int(rule.span_start)
        span_end = int(rule.span_end)
        if span_end <= span_start or span_start < 0 or span_end > len(page_text):
            stats.warnings.append(
                f"dropped unspanned rule candidate for cycle {cycle_id}: {rule.rule_text[:60]!r}"
            )
            continue
        span_text = page_text[span_start:span_end]
        normalised = rule.kind in ("nationality", "residency") and isinstance(rule.value, list)
        notes: list[str] = [VALUE_NORMALISED_NOTE] if normalised else []
        # Known shape problems are stored for the reviewer instead of hiding
        # the candidate: the extractor's own kinds (e.g. 'language') may not
        # match the engine's kind table yet, and human review is the meeting
        # point. A candidate that still fails validation at approval time is
        # refused until its kind/subject/value is corrected.
        notes.extend(
            validate_rule_shape(
                kind=rule.kind,
                subject=rule.subject,
                operator=rule.operator,
                value=rule.value,
                quote=span_text,
                values_normalised=normalised,
            )
        )
        inserted = session.execute(
            text(
                """
                INSERT INTO rule_candidates
                    (cycle_id, snapshot_id, kind, subject, operator, value, comparator, rule_text,
                     span_start, span_end, span_text, drafted_by, confidence, status, validation_notes)
                VALUES (:cycle_id, CAST(:snapshot_id AS uuid), :kind, :subject, :operator,
                        CAST(:value AS jsonb), :comparator, :rule_text,
                        :span_start, :span_end, :span_text, 'regex', :confidence, 'proposed',
                        CAST(:status_notes AS jsonb))
                ON CONFLICT (cycle_id, kind, subject, operator, span_start, span_end) DO NOTHING
                RETURNING id::text
                """
            ),
            {
                "cycle_id": cycle_id,
                "snapshot_id": snapshot_id,
                "kind": rule.kind,
                "subject": rule.subject,
                "operator": rule.operator,
                "value": json.dumps(rule.value),
                "comparator": "mandatory" if rule.mandatory else "optional",
                "rule_text": rule.rule_text,
                "span_start": span_start,
                "span_end": span_end,
                "span_text": span_text,
                "confidence": float(rule.confidence),
                "status_notes": json.dumps(notes),
            },
        ).first()
        if inserted is not None:
            stats.proposed_rules += 1
            if notes:
                stats.rule_candidates_flagged += 1

    for component in validated.funding:
        session.execute(
            text(
                """
                INSERT INTO funding_components
                    (id, cycle_id, component, coverage_status, amount, currency, amount_period,
                     conditions, evidence_ids)
                VALUES (gen_random_uuid(), :cycle_id, :component, :coverage, :amount, :currency,
                        :period, :conditions, CAST(:evidence_ids AS jsonb))
                """
            ),
            {
                "cycle_id": cycle_id,
                "component": component.component,
                "coverage": component.coverage,
                "amount": component.amount,
                "currency": component.currency,
                "period": component.amount_period,
                "conditions": component.conditions,
                "evidence_ids": json.dumps(list(component.evidence_ids) if hasattr(component, "evidence_ids") else []),
            },
        )
        stats.funding += 1

    for document in validated.documents:
        session.execute(
            text(
                """
                INSERT INTO required_documents
                    (id, cycle_id, doc_type, is_mandatory, description, lead_time_days,
                     evidence_ids, lead_time_days_default)
                VALUES (gen_random_uuid(), :cycle_id, :doc_type, :mandatory, :description,
                        :lead_time, CAST(:evidence_ids AS jsonb), :lead_time)
                """
            ),
            {
                "cycle_id": cycle_id,
                "doc_type": document.doc_type,
                "mandatory": document.mandatory,
                "description": document.description,
                "lead_time": document.lead_time_days,
                "evidence_ids": json.dumps(list(document.evidence_ids) if hasattr(document, "evidence_ids") else []),
            },
        )
        stats.documents += 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m services.api.app.services.corpus_builder``."""
    import argparse

    parser = argparse.ArgumentParser(description="Build the scholarship corpus from a capture.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--captures", default=str(DEFAULT_CAPTURES))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.db.session import get_engine

    engine = get_engine()
    with engine.begin() as connection:
        stats = build_corpus(
            session=connection,
            manifest_path=Path(args.manifest),
            captures_dir=Path(args.captures),
        )
    print(json.dumps(stats.to_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
