"""Tests for manifest loading, snapshotting and scam-signal collection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scholarmind.ingestion.fetcher import FetchResult, hash_content
from scholarmind.ingestion.manifest import due_sources, load_manifest
from scholarmind.ingestion.scam_signals import (
    collect_signals,
    detect_lookalike_domain,
    effective_trust_tier,
    summarise_signals,
)
from scholarmind.ingestion.snapshot import is_new_content, snapshot_from_fetch

MANIFEST = Path(__file__).resolve().parents[2] / "data" / "manifests" / "nigeria_v1.yaml"


def test_project_manifest_loads_and_validates() -> None:
    manifest = load_manifest(MANIFEST)
    assert manifest.corpus == "nigeria_v1"
    assert manifest.target_intake_year == 2027
    assert len(manifest) >= 20
    assert all(source.url.startswith("https://") for source in manifest)
    assert all(source.trust_tier in {"official_primary", "official_secondary", "partner", "aggregator"} for source in manifest)


def test_manifest_rejects_duplicate_urls(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        "corpus: test\nsources:\n"
        "  - url: https://a.org/x\n    name: A\n"
        "  - url: https://a.org/x\n    name: A again\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_manifest(manifest)


def test_manifest_rejects_non_http(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text("corpus: test\nsources:\n  - url: file:///etc/passwd\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(manifest)


def test_manifest_rejects_unknown_trust_tier(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        "corpus: test\nsources:\n  - url: https://a.org/x\n    trust_tier: super_official\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_manifest(manifest)


def test_due_sources_respects_cadence() -> None:
    manifest = load_manifest(MANIFEST)
    now = datetime.now(timezone.utc)

    never_checked = due_sources(manifest, {})
    assert len(never_checked) == len(manifest)

    just_checked = {source.url: now for source in manifest}
    assert due_sources(manifest, just_checked) == []

    long_ago = {source.url: now - timedelta(days=30) for source in manifest}
    assert len(due_sources(manifest, long_ago)) == len(manifest)


def test_snapshot_is_immutable_and_hashable() -> None:
    result = FetchResult(
        url="https://example.org/x",
        final_url="https://example.org/x",
        status_code=200,
        content=b"<html>hello</html>",
        content_type="text/html",
    )
    snapshot = snapshot_from_fetch(result, source_document_id="sd-1", text="hello")

    assert snapshot.content_hash == hash_content(b"<html>hello</html>")
    assert snapshot.text_hash
    with pytest.raises(Exception):
        snapshot.content_hash = "changed"  # type: ignore[misc]


def test_unchanged_content_is_not_a_change() -> None:
    result = FetchResult(
        url="https://example.org/x",
        final_url="https://example.org/x",
        status_code=200,
        content=b"body",
        content_type="text/html",
    )
    snapshot = snapshot_from_fetch(result, source_document_id="sd-1", text="body")

    assert is_new_content(None, snapshot)
    assert not is_new_content(snapshot.content_hash, snapshot)
    assert is_new_content("different", snapshot)


def test_lookalike_domain_is_flagged() -> None:
    signals = detect_lookalike_domain("https://chevening-apply.example.com/")
    assert signals
    assert signals[0].signal_type == "lookalike_domain"
    assert signals[0].severity == "high"


def test_official_domain_is_not_flagged() -> None:
    assert detect_lookalike_domain("https://www.chevening.com/scholarships/") == []


def test_high_severity_signal_demotes_trust_tier() -> None:
    signals = collect_signals(
        url="https://chevening-apply.example.com/",
        text="Pay an application fee of $50 by bank transfer. No contact details here.",
        trust_tier="official_primary",
    )
    assert effective_trust_tier("official_primary", signals) == "aggregator"
    summary = summarise_signals(signals)
    assert summary["total"] >= 2
    assert summary["highest_severity"] == "high"


def test_trusted_source_fee_language_is_not_flagged() -> None:
    signals = collect_signals(
        url="https://www.chevening.com/x",
        text="An application fee of $50 applies.",
        trust_tier="official_primary",
    )
    assert all(signal.signal_type != "application_fee" for signal in signals)
