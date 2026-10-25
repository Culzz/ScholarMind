"""Chunk spans must point back at the exact text they came from.

A citation is only checkable if ``text[start:end]`` equals the quoted passage,
so these tests assert the span arithmetic rather than the chunk count.
"""

from __future__ import annotations

from scholarmind.retrieval.fusion import chunk_spans, chunk_text


def test_spans_slice_the_original_text() -> None:
    text = " ".join(f"Sentence {index} about applications." for index in range(200))
    chunks = chunk_spans(text, max_tokens=50, overlap=10)

    assert len(chunks) > 1
    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text
        assert chunk.text


def test_spans_ignore_leading_whitespace_without_moving_the_offset() -> None:
    text = "\n\n   Applications close on 12 November 2026.   \n\n"

    chunks = chunk_spans(text, max_tokens=100, overlap=0)

    assert len(chunks) == 1
    assert chunks[0].text == "Applications close on 12 November 2026."
    assert text[chunks[0].start : chunks[0].end] == chunks[0].text


def test_chunk_text_is_the_text_of_the_spans() -> None:
    text = "A" * 2000

    assert chunk_text(text, max_tokens=100, overlap=10) == [
        chunk.text for chunk in chunk_spans(text, max_tokens=100, overlap=10)
    ]


def test_empty_text_has_no_chunks() -> None:
    assert chunk_spans("   \n\t ") == []
    assert chunk_text("") == []


def test_overlap_must_be_smaller_than_the_budget() -> None:
    import pytest

    with pytest.raises(ValueError):
        chunk_spans("text", max_tokens=10, overlap=10)
