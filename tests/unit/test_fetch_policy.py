"""The `fetch_policy` contract: bots never hammer pages that cannot answer.

A `manual` policy entry is unreachable from the fetcher's network by
definition (DNS, geo or timeout) - the record is entered by hand with
provenance or it does not exist. A `browser` policy entry needs the headless
adapter. Both must be invisible to the scheduler/crawler rather than turned
into repeated refusals, and neither may fabricate database records.
"""

from __future__ import annotations

import textwrap

import pytest

from scholarmind.ingestion.capture import capture_manifest
from scholarmind.ingestion.manifest import Manifest, SourceEntry, load_manifest


def _manifest_entry_url(manifest: Manifest, name: str) -> str:
    for source in manifest.sources:
        if source.name == name:
            return source.url
    raise AssertionError(name)


def test_load_manifest_parses_fetch_policy(tmp_path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        textwrap.dedent(
            """
            version: 2
            corpus: test
            target_intake_year: 2027
            sources:
              - url: https://a.edu.ng/
                name: Direct
                provider_type: university
              - url: https://b.edu.ng/
                name: Blocked
                provider_type: university
                fetch_policy: browser
              - url: https://c.edu.ng/
                name: Unreachable
                provider_type: university
                fetch_policy: manual
            """
        ),
        encoding="utf-8",
    )
    manifest = load_manifest(manifest_file)
    policies = {source.name: (source.fetch_policy, source.requires_render) for source in manifest}
    assert policies == {
        "Direct": ("direct", False),
        "Blocked": ("browser", True),
        "Unreachable": ("manual", False),
    }


def test_load_manifest_rejects_an_unknown_fetch_policy(tmp_path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        textwrap.dedent(
            """
            version: 2
            corpus: test
            target_intake_year: 2027
            sources:
              - url: https://a.edu.ng/
                name: Sneaky
                provider_type: university
                fetch_policy: ignore_robots
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fetch_policy"):
        load_manifest(manifest_file)


def test_manual_sources_are_never_scheduled_for_a_sweep() -> None:
    blocked = SourceEntry(url="https://b.edu.ng/", name="Blocked", fetch_policy="browser")
    manual = SourceEntry(url="https://c.edu.ng/", name="Unreachable", fetch_policy="manual")
    manifest = Manifest(corpus="test", target_intake_year=2027, sources=(blocked, manual))
    due = {source.url for source in _due(manifest)}
    assert "https://c.edu.ng/" not in due, "a manual entry must never be crawled automatically"
    assert "https://b.edu.ng/" in due


def _due(manifest: Manifest):
    from scholarmind.ingestion.manifest import due_sources

    return due_sources(manifest, last_checked={})


def test_capture_never_attempts_a_manual_source(tmp_path) -> None:
    attempted: list[str] = []

    class _Fetcher:
        def fetch_text(self, url: str, **kwargs):  # pragma: no cover - must not be called
            attempted.append(url)
            raise AssertionError("a manual source was fetched")

    manual = SourceEntry(url="https://c.edu.ng/", name="Unreachable", fetch_policy="manual")
    manifest = Manifest(corpus="test", target_intake_year=2027, sources=(manual,))

    results = capture_manifest(
        manifest,
        output_dir=tmp_path,
        delay_seconds=0,
        fetcher_factory=lambda source: _Fetcher(),
    )

    assert attempted == []
    assert len(results) == 1
    result = results[0]
    assert result.ok is False
    assert "manual" in (result.error or "")
    assert result.path is None
