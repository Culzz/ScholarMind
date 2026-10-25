"""Retrieval must name the mode it actually ran.

A lexical-only search used to be reported as ``hybrid`` whenever the caller
asked for hybrid, and a dense list whose vectors had the wrong dimension was
silently dropped. Both made a degraded result look complete.
"""

from __future__ import annotations

import pytest

from services.api.app.services import retrieval as service


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Session:
    """Enough of a session for the dense query's one SELECT."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, *args, **kwargs):
        return _Result(self.rows)


def test_hybrid_without_an_embedding_is_named_lexical_fallback() -> None:
    session = _Session([])

    result = service.retrieve(session, "chevening deadline", embedding=None, mode="hybrid")

    assert result.mode == "hybrid"
    assert result.mode_used == "lexical_fallback"
    assert result.degraded_reason == "no_query_embedding"
    assert result.embedding_available is False


def test_dense_without_an_embedding_returns_nothing_and_says_why() -> None:
    session = _Session([])

    result = service.retrieve(session, "chevening deadline", embedding=None, mode="dense")

    assert result.chunks == []
    assert result.mode_used == "unavailable"
    assert result.degraded_reason == "no_query_embedding"


def test_dense_rejects_a_dimension_mismatch() -> None:
    session = _Session([("chunk-1", [0.1, 0.2, 0.3])])

    with pytest.raises(ValueError, match="dimension mismatch"):
        service.retrieve(session, "chevening deadline", embedding=[0.1, 0.2], mode="dense")


def test_hybrid_with_a_dense_hit_is_named_hybrid() -> None:
    session = _Session([("chunk-1", [1.0, 0.0])])

    class _Hybrid(_Session):
        def __init__(self):
            super().__init__([("chunk-1", [1.0, 0.0])])
            self.calls = 0

        def execute(self, statement, params=None):
            self.calls += 1
            if "FROM evidence_chunks c" in str(statement) and "embedding IS NOT NULL" in str(statement):
                return _Result(self.rows)
            if "FROM evidence_chunks c" in str(statement) and "ts_rank_cd" in str(statement):
                return _Result([("chunk-1", 0.9)])
            return _Result([])

    result = service.retrieve(_Hybrid(), "chevening deadline", embedding=[1.0, 0.0], mode="hybrid")

    assert result.mode_used == "hybrid"
    assert result.dense_count == 1
    assert result.lexical_count == 1
