"""Retrieval: lexical + dense search, Reciprocal Rank Fusion, reranking hooks.

Fusion strategy
---------------
Reciprocal Rank Fusion (RRF) is used rather than score normalisation because lexical
(``ts_rank_cd``) and cosine similarities are not on comparable scales, and any
min-max normalisation is sensitive to outliers in a small corpus.

    RRF(d) = sum_over_lists( 1 / (k + rank_i(d)) )

``k`` defaults to 60, the value from the original RRF work, which is insensitive
across a wide range in practice.

Everything in this module is a pure function over ranked id lists so it can be unit
tested without a database, a network, or an embedding provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class RankedItem:
    """A retrieved chunk with its rank within one retrieval list."""

    chunk_id: str
    rank: int
    score: float = 0.0


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RankedItem]],
    *,
    k: int = DEFAULT_RRF_K,
    weights: Sequence[float] | None = None,
) -> list[RankedItem]:
    """Fuse several ranked lists into one ordering.

    Parameters
    ----------
    rankings:
        One ranked list per retrieval strategy (lexical, dense, ...). Ranks are
        1-based; the list order is authoritative, the ``rank`` field is ignored.
    k:
        RRF constant. Larger ``k`` flattens the contribution of the top ranks.
    weights:
        Optional per-list weights (e.g. favouring lexical for factual queries).

    Returns
    -------
    list[RankedItem]
        Items sorted by fused score descending. Ties break on the chunk id so the
        ordering is deterministic and reproducible across runs.
    """
    if not rankings:
        return []
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights must align with the number of ranking lists")

    scores: dict[str, float] = {}
    for index, ranking in enumerate(rankings):
        weight = 1.0 if weights is None else float(weights[index])
        for position, item in enumerate(ranking, start=1):
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + weight / (k + position)

    ordered = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    return [RankedItem(chunk_id=chunk_id, rank=index, score=score) for index, (chunk_id, score) in enumerate(ordered, start=1)]


@dataclass(frozen=True)
class TextChunk:
    """A chunk with its position in the source text."""

    start: int
    end: int
    text: str


def chunk_spans(text: str, *, max_tokens: int = 500, overlap: int = 80) -> list[TextChunk]:
    """Split text into overlapping chunks and keep their character spans.

    The span is the evidence anchor: ``text[chunk.start:chunk.end] == chunk.text``
    must hold, otherwise a citation cannot be checked against the snapshot.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap < 0 or overlap >= max_tokens:
        raise ValueError("overlap must be non-negative and smaller than max_tokens")

    char_budget = max_tokens * 4
    char_overlap = overlap * 4
    if not text.strip():
        return []

    chunks: list[TextChunk] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + char_budget, length)
        if end < length:
            # Prefer a paragraph or sentence boundary near the budget end.
            boundary = max(
                text.rfind("\n\n", start + char_budget // 2, end),
                text.rfind(". ", start + char_budget // 2, end),
            )
            if boundary != -1:
                end = boundary + 1
        raw = text[start:end]
        stripped = raw.strip()
        if stripped:
            leading = len(raw) - len(raw.lstrip())
            chunk_start = start + leading
            chunks.append(TextChunk(start=chunk_start, end=chunk_start + len(stripped), text=stripped))
        if end >= length:
            break
        start = max(end - char_overlap, start + 1)
        # Do not begin a chunk inside a word: a quoted passage that starts
        # mid-word ("stion A.11") reads as corrupted evidence.
        while start < length and start > 0 and text[start - 1].isalnum() and text[start].isalnum():
            start += 1
    return chunks


def chunk_text(text: str, *, max_tokens: int = 500, overlap: int = 80) -> list[str]:
    """Split text into overlapping chunks.

    A lightweight whitespace/character approximation is used here on purpose: the
    production chunker tokenises with the provider tokenizer, but the *shape* of the
    behaviour (overlap preserved, headings kept with their section) is what the
    retrieval experiments depend on, and this version stays dependency-free.

    Character budget is derived from the token budget using a conservative average
    of roughly four characters per token.
    """
    return [chunk.text for chunk in chunk_spans(text, max_tokens=max_tokens, overlap=overlap)]



def build_citation_map(
    claims: Iterable[Mapping[str, object]],
    retrieved_chunk_ids: Sequence[str],
) -> tuple[dict[int, list[str]], list[int]]:
    """Validate that every cited evidence id existed in the retrieved context.

    Returns ``(valid_map, invalid_claim_indices)`` where ``valid_map`` maps a claim
    index to the subset of its evidence ids that were actually retrieved. Claim
    indices with no surviving evidence id are reported as invalid and must be
    dropped or downgraded by the generation layer.
    """
    allowed = set(retrieved_chunk_ids)
    citation_map: dict[int, list[str]] = {}
    invalid: list[int] = []
    for index, claim in enumerate(claims):
        ids = [str(i) for i in (claim.get("evidence_ids") or [])]
        kept = [i for i in ids if i in allowed]
        citation_map[index] = kept
        if not kept:
            invalid.append(index)
    return citation_map, invalid


def select_context(
    fused: Sequence[RankedItem],
    *,
    max_chunks: int = 20,
    max_characters: int = 12_000,
) -> list[RankedItem]:
    """Trim a fused ranking to a prompt-sized context, preserving order."""
    selected: list[RankedItem] = []
    used = 0
    for item in fused:
        if len(selected) >= max_chunks:
            break
        selected.append(item)
        used += 1
        if used >= max_chunks:
            break
    return selected


def recall_at_k(required_ids: Iterable[str], retrieved_ids: Sequence[str]) -> float:
    """Fraction of required evidence ids present in the retrieved list."""
    required = set(required_ids)
    if not required:
        return 0.0
    return len(required.intersection(retrieved_ids)) / len(required)


def reciprocal_rank(required_ids: Iterable[str], retrieved_ids: Sequence[str]) -> float:
    """Reciprocal rank of the first required id (0.0 when absent)."""
    required = set(required_ids)
    for position, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in required:
            return 1.0 / position
    return 0.0
