"""The LLM drafting pass: passages in, validated rule candidates out.

This is the driver behind ``python -m app.cli draft-rules``. It selects
evidence chunks whose text looks like eligibility prose, asks the configured
generation provider to propose structured rules, validates every candidate
against its own quote, and stores only the survivors in ``rule_candidates``
with ``drafted_by='llm'``. Rejections and parse failures are counted and
reported; they never enter the queue, and the pass never decides eligibility -
approval happens in the review queue, by a human.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.core.config import Settings
from app.core.llm import AnthropicProvider
from scholarmind.extraction.rule_drafter import (
    DraftCandidate,
    draft_rules_for_text,
)

# Keywords that mark a chunk as eligibility prose. Precision matters more than
# recall here: a missed chunk costs an unprompted rule, a noisy chunk costs a
# wasted LLM call.
ELIGIBILITY_KEYWORDS = (
    "eligible",
    "eligibility",
    "must hold",
    "must have",
    "must be",
    "degree",
    "nationality",
    "citizen",
    "resident",
    "band",
    "second class",
    "grade",
)


def _provider(settings: Settings) -> Any:
    from app.core.llm import build_generation_provider

    provider = build_generation_provider(settings)
    if provider is None:
        raise RuntimeError(
            "LLM_API_KEY is not configured. Drafting needs generation provider access; "
            "set LLM_API_KEY (plus LLM_PROVIDER=anthropic for Anthropic; the default "
            "provider is OpenAI-compatible) in the environment."
        )
    return provider


def _draft_targets(
    session: Any, limit: int, scholarship_id: str | None
) -> list[dict[str, Any]]:
    """Chunks that look like eligibility prose, with their page offset."""
    keyword_clauses = [
        "ch.content ILIKE :kw%d" % i for i in range(len(ELIGIBILITY_KEYWORDS))
    ]
    params: dict[str, Any] = {"limit": limit}
    for i, keyword in enumerate(ELIGIBILITY_KEYWORDS):
        params[f"kw{i}"] = f"%{keyword}%"
    extra: list[str] = []
    if scholarship_id:
        extra.append("sd.scholarship_id::text = :scholarship_id")
        params["scholarship_id"] = scholarship_id
    where = " AND ".join([f"({ ' OR '.join(keyword_clauses) })", "sd.scholarship_id IS NOT NULL", *extra])
    rows = session.execute(
        text(
            f"""
            SELECT ch.id::text AS chunk_id, ch.content, ch.char_start,
                   ch.snapshot_id::text AS snapshot_id, sd.url,
                   sd.scholarship_id::text AS scholarship_id,
                   cyc.cycle_id::text AS cycle_id
            FROM evidence_chunks ch
            JOIN source_documents sd ON sd.id = ch.source_document_id
            LEFT JOIN LATERAL (
                SELECT c.id::text AS cycle_id
                FROM scholarship_cycles c
                WHERE c.scholarship_id = sd.scholarship_id
                ORDER BY c.is_current DESC, c.intake_year DESC
                LIMIT 1
            ) cyc ON true
            WHERE {where}
            ORDER BY ch.id
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def draft_rules(
    session: Any,
    settings: Settings,
    *,
    limit_chunks: int = 40,
    scholarship_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Draft candidates for up to ``limit_chunks`` passages."""
    report: dict[str, Any] = {
        "chunks_seen": 0,
        "chunks_without_current_cycle": 0,
        "parse_failures": 0,
        "candidates_inserted": 0,
        "candidates_rejected": 0,
        "dry_run": dry_run,
        "rejections": [],
    }
    targets = _draft_targets(session, limit_chunks, scholarship_id)
    report["chunks_seen"] = len(targets)
    if not targets:
        return report

    provider = _provider(settings)
    for target in targets:
        if not target["cycle_id"]:
            report["chunks_without_current_cycle"] += 1
            continue
        outcome = draft_rules_for_text(
            provider,
            target["content"],
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
        if outcome.parse_error:
            report["parse_failures"] += 1
            report["rejections"].append(
                {"chunk_id": target["chunk_id"], "reason": outcome.parse_error}
            )
            continue
        report["candidates_rejected"] += len(outcome.rejected)
        report["rejections"].extend(
            {"chunk_id": target["chunk_id"], **rejection} for rejection in outcome.rejected
        )
        for candidate in outcome.candidates:
            _insert_candidate(session, target, candidate, settings, dry_run=dry_run)
            report["candidates_inserted"] += 0 if dry_run else 1
    if not dry_run:
        session.commit()
    return report


def _insert_candidate(
    session: Any,
    target: dict[str, Any],
    candidate: DraftCandidate,
    settings: Settings,
    *,
    dry_run: bool,
) -> None:
    """Insert one validated candidate with page-relative spans."""
    # Chunk spans are page-relative already (char_start is the chunk's own
    # offset in the page), so shifts are simply added.
    offset = int(target["char_start"])
    page_span_start = offset + candidate.span_start
    page_span_end = offset + candidate.span_end
    span_text = target["content"][candidate.span_start : candidate.span_end]
    if dry_run:
        return
    session.execute(
        text(
            """
            INSERT INTO rule_candidates
                (chunk_id, snapshot_id, cycle_id, kind, subject, operator, value, comparator,
                 rule_text, span_start, span_end, span_text, doc_url, drafted_by, model_id,
                 confidence, status, validation_notes)
            VALUES (CAST(:chunk_id AS uuid), CAST(:snapshot_id AS uuid), CAST(:cycle_id AS uuid),
                    :kind, :subject, :operator, CAST(:value AS jsonb), :comparator,
                    :rule_text, :span_start, :span_end, :span_text, :doc_url, 'llm',
                    :model_id, :confidence, 'proposed', '[]'::jsonb)
            ON CONFLICT (cycle_id, kind, subject, operator, span_start, span_end) DO NOTHING
            """
        ),
        {
            "chunk_id": target["chunk_id"],
            "snapshot_id": target["snapshot_id"],
            "cycle_id": target["cycle_id"],
            "kind": candidate.kind,
            "subject": candidate.subject,
            "operator": candidate.operator,
            "value": json.dumps(candidate.value) if candidate.value is not None else "null",
            "comparator": "mandatory" if candidate.mandatory else "optional",
            "rule_text": candidate.rule_text,
            "span_start": page_span_start,
            "span_end": page_span_end,
            "span_text": span_text,
            "doc_url": target["url"],
            "model_id": settings.llm_model,
            "confidence": max(0.0, min(1.0, candidate.confidence)),
        },
    )
