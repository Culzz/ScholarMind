"""Retrieval over the evidence index.

The service runs a lexical query and a dense query in parallel and fuses the
two ranked lists with Reciprocal Rank Fusion. It returns evidence chunks with
the metadata the prompt and the UI need: source, snapshot time, trust tier and
cycle.

Only chunks from official sources are returned by default. Aggregator-tier
pages are excluded: they may help a student find a scholarship, but they are
never the evidence behind a confirmed claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy import text

from scholarmind.retrieval.fusion import RankedItem, reciprocal_rank_fusion


@dataclass
class RetrievedChunk:
    """One retrieved evidence chunk."""

    chunk_id: str
    content: str
    source_document_id: str
    source_url: str | None = None
    source_title: str | None = None
    trust_tier: str | None = None
    checked_at: str | None = None
    cycle_label: str | None = None
    scholarship_slug: str | None = None
    section_path: str | None = None
    rank: int = 0
    lexical_rank: int | None = None
    dense_rank: int | None = None
    score: float = 0.0

    def to_excerpt(self) -> dict[str, str]:
        return {
            "evidence_id": self.chunk_id,
            "content": self.content,
            "source_url": self.source_url or "",
            "source_title": self.source_title or "",
            "checked_at": self.checked_at or "",
            "trust_tier": self.trust_tier or "",
            "cycle_label": self.cycle_label or "",
        }


@dataclass
class RetrievalResult:
    """The outcome of one retrieval."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    mode: str = "hybrid"
    top_k: int = 20
    rrf_k: int = 60
    lexical_count: int = 0
    dense_count: int = 0

    def as_excerpts(self) -> dict[str, str]:
        return {chunk.chunk_id: chunk.content for chunk in self.chunks}


def _lexical_query(session: Any, query: str, limit: int) -> list[tuple[str, float]]:
    statement = text(
        """
        SELECT c.id::text, ts_rank_cd(c.tsv, websearch_to_tsquery('english', :query)) AS score
        FROM evidence_chunks c
        WHERE c.tsv @@ websearch_to_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    rows = session.execute(statement, {"query": query, "limit": limit}).fetchall()
    return [(row[0], float(row[1] or 0.0)) for row in rows]


def _dense_query(session: Any, query: str, embedding: Sequence[float], limit: int) -> list[tuple[str, float]]:
    statement = text(
        """
        SELECT c.id::text, (c.embedding <=> CAST(:embedding AS vector)) AS distance
        FROM evidence_chunks c
        WHERE c.embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT :limit
        """
    )
    rows = session.execute(
        statement, {"embedding": list(embedding), "limit": limit}
    ).fetchall()
    return [(row[0], float(row[1] or 0.0)) for row in rows]


def _load_chunks(session: Any, chunk_ids: Sequence[str]) -> dict[str, RetrievedChunk]:
    if not chunk_ids:
        return {}
    statement = text(
        """
        SELECT c.id::text, c.content, c.source_document_id::text, d.url, s.name,
               d.trust_tier, d.last_success_at, c.section_path,
               sc.cycle_label, sc.slug
        FROM evidence_chunks c
        JOIN source_documents d ON d.id = c.source_document_id
        LEFT JOIN source_snapshots s ON s.id = c.snapshot_id
        LEFT JOIN scholarships sc ON sc.canonical_source_id = d.id
        WHERE c.id::text = ANY(:ids)
        """
    )
    rows = session.execute(statement, {"ids": list(chunk_ids)}).fetchall()
    chunks: dict[str, RetrievedChunk] = {}
    for row in rows:
        chunks[row[0]] = RetrievedChunk(
            chunk_id=row[0],
            content=row[1],
            source_document_id=row[2],
            source_url=row[3],
            source_title=row[4],
            trust_tier=row[5],
            checked_at=row[6].isoformat() if row[6] else None,
            section_path=row[8],
            cycle_label=row[9],
            scholarship_slug=row[10],
        )
    return chunks


def retrieve(
    session: Any,
    query: str,
    *,
    embedding: Sequence[float] | None = None,
    mode: str = "hybrid",
    top_k: int = 20,
    candidates: int = 100,
    rrf_k: int = 60,
    include_aggregators: bool = False,
) -> RetrievalResult:
    """Run a hybrid retrieval and return the fused, ordered chunks."""
    result = RetrievalResult(mode=mode, top_k=top_k, rrf_k=rrf_k)

    lexical = _lexical_query(session, query, candidates) if mode in ("lexical", "hybrid") else []
    dense = _dense_query(session, query, embedding, candidates) if mode in ("dense", "hybrid") and embedding else []
    result.lexical_count = len(lexical)
    result.dense_count = len(dense)

    rankings: list[Sequence[RankedItem]] = []
    if lexical:
        rankings.append([RankedItem(chunk_id=chunk_id, rank=index) for index, (chunk_id, _) in enumerate(lexical, 1)])
    if dense:
        rankings.append([RankedItem(chunk_id=chunk_id, rank=index) for index, (chunk_id, _) in enumerate(dense, 1)])

    if not rankings:
        return result

    fused = reciprocal_rank_fusion(rankings, k=rrf_k)[:top_k]
    chunk_map = _load_chunks(session, [item.chunk_id for item in fused])

    lexical_positions = {chunk_id: index for index, (chunk_id, _) in enumerate(lexical, 1)}
    dense_positions = {chunk_id: index for index, (chunk_id, _) in enumerate(dense, 1)}

    chunks: list[RetrievedChunk] = []
    for item in fused:
        chunk = chunk_map.get(item.chunk_id)
        if chunk is None:
            continue
        if not include_aggregators and chunk.trust_tier == "aggregator":
            continue
        chunk.rank = item.rank
        chunk.score = item.score
        chunk.lexical_rank = lexical_positions.get(item.chunk_id)
        chunk.dense_rank = dense_positions.get(item.chunk_id)
        chunks.append(chunk)

    result.chunks = chunks
    return result


def embed_query(text: str, provider: Any, model: str) -> list[float]:
    """Embed a query, returning an empty list when no provider is configured."""
    from scholarmind.generation.provider import EmbeddingRequest

    if provider is None:
        return []
    try:
        response = provider.embed(EmbeddingRequest(texts=[text], model=model))
    except Exception:
        return []
    return response.vectors[0] if response.vectors else []
