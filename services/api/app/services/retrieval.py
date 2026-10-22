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

import json
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


_QUERY_STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "and", "or", "is", "are", "was",
    "were", "be", "been", "do", "does", "did", "what", "when", "where", "which", "who",
    "how", "why", "can", "could", "should", "would", "will", "shall", "may", "might",
    "my", "me", "i", "you", "your", "it", "its", "that", "this", "with", "about",
}


def _build_tsquery(query: str) -> str | None:
    """Build a PostgreSQL text-search query from a natural-language question.

    ``websearch_to_tsquery`` is AND-based: "tuition fees and stipend" matches
    only chunks containing every term, which returned nothing on the real
    corpus. Search should retrieve candidates and let the ranking decide, so the
    terms are combined with OR and ``ts_rank_cd`` rewards documents that cover
    more of them. Quoted phrases keep their phrase semantics.
    """
    import re

    stripped = query.strip()
    if not stripped:
        return None

    if '"' in stripped:
        return stripped

    terms = [
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", stripped)
        if token.lower() not in _QUERY_STOPWORDS and len(token) > 1
    ]
    if not terms:
        return None

    unique: list[str] = []
    for term in terms:
        if term.lower() not in {existing.lower() for existing in unique}:
            unique.append(term)
    return " | ".join(unique)


def _lexical_query(session: Any, query: str, limit: int) -> list[tuple[str, float]]:
    tsquery = _build_tsquery(query)
    if not tsquery:
        return []
    statement = text(
        """
        SELECT c.id::text, ts_rank_cd(c.tsv, to_tsquery('english', :tsquery)) AS score
        FROM evidence_chunks c
        WHERE c.tsv @@ to_tsquery('english', :tsquery)
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    rows = session.execute(statement, {"tsquery": tsquery, "limit": limit}).fetchall()
    return [(row[0], float(row[1] or 0.0)) for row in rows]


def _dense_query(session: Any, query: str, embedding: Sequence[float], limit: int) -> list[tuple[str, float]]:
    """Rank chunks by cosine similarity to the query embedding.

    Two backends are supported. With pgvector installed the database does the
    ranking with an ANN index. Without it, the vectors are fetched and ranked
    in Python - which is adequate at the corpus sizes this platform targets,
    and keeps the deployment working on a plain PostgreSQL server.
    """
    statement = text(
        """
        SELECT c.id::text, c.embedding
        FROM evidence_chunks c
        WHERE c.embedding IS NOT NULL
        LIMIT 5000
        """
    )
    rows = session.execute(statement).fetchall()

    query_vector = list(embedding)
    if not query_vector:
        return []

    scored: list[tuple[str, float]] = []
    for row in rows:
        stored = row[1]
        if stored is None:
            continue
        if isinstance(stored, str):
            try:
                stored = json.loads(stored)
            except json.JSONDecodeError:
                continue
        vector = list(stored)
        if len(vector) != len(query_vector):
            continue
        similarity = _cosine(query_vector, vector)
        scored.append((row[0], similarity))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors."""
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / ((left_norm**0.5) * (right_norm**0.5))


def _load_chunks(session: Any, chunk_ids: Sequence[str]) -> dict[str, RetrievedChunk]:
    if not chunk_ids:
        return {}
    statement = text(
        """
        SELECT c.id::text, c.content, c.source_document_id::text, d.url,
               meta.scholarship_name, d.trust_tier, d.last_success_at, c.section_path,
               meta.cycle_label, meta.slug
        FROM evidence_chunks c
        JOIN source_documents d ON d.id = c.source_document_id
        LEFT JOIN LATERAL (
            SELECT s.name AS scholarship_name, s.slug,
                   (SELECT c2.cycle_label FROM scholarship_cycles c2
                     WHERE c2.scholarship_id = s.id
                     ORDER BY c2.is_current DESC, c2.intake_year DESC LIMIT 1) AS cycle_label
            FROM scholarships s
            WHERE s.canonical_source_id = d.id
            ORDER BY s.name
            LIMIT 1
        ) meta ON true
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
            section_path=row[7],
            cycle_label=row[8],
            scholarship_slug=row[9],
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
