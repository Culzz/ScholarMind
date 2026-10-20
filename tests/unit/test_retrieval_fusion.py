"""Unit tests for retrieval fusion and citation mapping."""

from __future__ import annotations

from scholarmind.retrieval.fusion import (
    RankedItem,
    build_citation_map,
    chunk_text,
    recall_at_k,
    reciprocal_rank,
    reciprocal_rank_fusion,
)


def _items(ids: list[str]) -> list[RankedItem]:
    return [RankedItem(chunk_id=i, rank=index) for index, i in enumerate(ids, start=1)]


def test_rrf_prefers_items_found_in_both_lists() -> None:
    lexical = _items(["a", "b", "c"])
    dense = _items(["c", "a", "d"])
    fused = reciprocal_rank_fusion([lexical, dense])

    assert fused[0].chunk_id == "a"
    assert fused[1].chunk_id == "c"
    assert {item.chunk_id for item in fused} == {"a", "b", "c", "d"}


def test_rrf_is_deterministic_on_ties() -> None:
    fused = reciprocal_rank_fusion([_items(["x", "y"]), _items(["y", "x"])])
    assert [i.chunk_id for i in fused] == sorted([i.chunk_id for i in fused])


def test_rrf_weights_change_order() -> None:
    lexical = _items(["a"])
    dense = _items(["b"])
    unweighted = reciprocal_rank_fusion([lexical, dense])
    weighted = reciprocal_rank_fusion([lexical, dense], weights=[5.0, 1.0])
    assert unweighted[0].chunk_id == weighted[0].chunk_id == "a"


def test_rrf_with_no_lists_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []


def test_citation_map_drops_unknown_evidence_ids() -> None:
    claims = [
        {"text": "a", "evidence_ids": ["ev_1", "ev_missing"]},
        {"text": "b", "evidence_ids": ["ev_unknown"]},
    ]
    citation_map, invalid = build_citation_map(claims, ["ev_1", "ev_2"])
    assert citation_map == {0: ["ev_1"], 1: []}
    assert invalid == [1]


def test_chunking_produces_overlapping_chunks() -> None:
    text = "Sentence one. " * 400
    chunks = chunk_text(text, max_tokens=50, overlap=10)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_chunking_rejects_invalid_overlap() -> None:
    try:
        chunk_text("abc", max_tokens=10, overlap=10)
    except ValueError:
        return
    raise AssertionError("expected ValueError for overlap >= max_tokens")


def test_recall_and_reciprocal_rank() -> None:
    assert recall_at_k(["a", "b"], ["b", "c"]) == 0.5
    assert reciprocal_rank(["a", "b"], ["c", "a"]) == 0.5
    assert reciprocal_rank(["z"], ["a"]) == 0.0
