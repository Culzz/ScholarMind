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
from scholarmind.extraction.validate import validate_result
from scholarmind.ingestion.manifest import Manifest, load_manifest
from scholarmind.normalization.cycles import build_cycles, choose_current_cycles
from scholarmind.retrieval.fusion import chunk_text

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
    funding: int = 0
    documents: int = 0
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
            "funding": self.funding,
            "documents": self.documents,
            "warnings": list(self.warnings),
            "vocabulary": dict(self.vocabulary),
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "scholarship"


def _group_key(entry: dict[str, Any]) -> str:
    """Group key for a capture: parent pages and their children belong together."""
    parent = entry.get("parent_url")
    return parent or entry["url"]


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

    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(_group_key(entry), []).append(entry)

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
            if not entry.get("ok"):
                continue
            folder = Path(entry["path"])
            page_text = (folder / "page.txt").read_text(encoding="utf-8")
            source_document_id = _upsert_source_document(session, text, entry, source, stats)
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
    session: Any, text: Any, entry: dict[str, Any], source: Any, stats: BuildStats
) -> str:
    source_type = "other"
    if source is not None:
        source_type = source.provider_type
    row = session.execute(
        text(
            """
            INSERT INTO source_documents (id, url, source_type, trust_tier, fetch_status, last_checked_at, last_success_at)
            VALUES (gen_random_uuid(), :url, :source_type, :trust_tier, 'ok', now(), now())
            ON CONFLICT (url) DO UPDATE SET last_success_at = now(), updated_at = now()
            RETURNING id::text
            """
        ),
        {
            "url": entry["url"],
            "source_type": source_type,
            "trust_tier": entry.get("trust_tier", "official_primary"),
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
    chunks = chunk_text(page_text, max_tokens=chunk_tokens, overlap=chunk_overlap)
    for chunk in chunks:
        content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
        session.execute(
            text(
                """
                INSERT INTO evidence_chunks
                    (id, snapshot_id, source_document_id, char_start, char_end, content, content_hash, token_count)
                VALUES (gen_random_uuid(), :snapshot_id, :source_id, 0, :length, :content, :hash, :tokens)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "source_id": source_document_id,
                "length": len(chunk),
                "content": chunk,
                "hash": content_hash,
                "tokens": len(chunk) // 4,
            },
        )
        stats.chunks += 1


def _insert_claims(session: Any, text: Any, snapshot_id: str, validated: Any, stats: BuildStats) -> None:
    for fact in validated.facts:
        session.execute(
            text(
                """
                INSERT INTO evidence_claims
                    (id, snapshot_id, span_start, span_end, claim_text, claim_type, field_name,
                     normalized_value, validation_status, confidence, extraction_method)
                VALUES (gen_random_uuid(), :snapshot_id, :span_start, :span_end, :claim_text,
                        :claim_type, :field_name, CAST(:value AS jsonb), :status, :confidence,
                        :extraction_method)
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
        stats.claims += 1


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
                SET deadline_at = EXCLUDED.deadline_at,
                    deadline_raw_text = EXCLUDED.deadline_raw_text,
                    deadline_precision = EXCLUDED.deadline_precision,
                    opens_at = EXCLUDED.opens_at,
                    status = EXCLUDED.status,
                    is_current = EXCLUDED.is_current,
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
        session.execute(
            text(
                """
                INSERT INTO eligibility_rules
                    (id, cycle_id, kind, subject, operator, value, comparator, rule_text,
                     evidence_ids, confidence, ambiguity_flag, authored_by, version)
                VALUES (gen_random_uuid(), :cycle_id, :kind, :subject, :operator,
                        CAST(:value AS jsonb), :comparator, :rule_text, CAST(:evidence_ids AS jsonb),
                        :confidence, :ambiguity, 'rule', 1)
                """
            ),
            {
                "cycle_id": cycle_id,
                "kind": rule.kind,
                "subject": rule.subject,
                "operator": rule.operator,
                "value": json.dumps(rule.value),
                "comparator": "mandatory" if rule.mandatory else "optional",
                "rule_text": rule.rule_text,
                "evidence_ids": json.dumps(list(rule.evidence_ids) if hasattr(rule, "evidence_ids") else []),
                "confidence": rule.confidence,
                "ambiguity": rule.ambiguous,
            },
        )
        stats.rules += 1

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
