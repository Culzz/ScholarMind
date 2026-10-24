"""Crawl de-duplication and root grouping.

The same page is regularly linked from several sources. Capturing it once per
source produced duplicate snapshots and split a single programme into several
awards in the catalogue, so these tests pin the behaviour down.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from scholarmind.ingestion.capture import _url_key, capture_manifest
from scholarmind.ingestion.manifest import Manifest, SourceEntry


@dataclass
class _FakeFetch:
    url: str
    html: str

    status_code: int = 200
    error: str | None = None
    final_url: str = ""
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.final_url = self.url
        self.headers = {"content-type": "text/html; charset=utf-8"}

    @property
    def ok(self) -> bool:
        return True

    @property
    def content(self) -> bytes:
        return self.html.encode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


PAGES = {
    "https://example.org/scholarship": (
        "<html><body><main><h1>Scholarship</h1>"
        '<a href="/eligibility">Eligibility</a>'
        '<a href="/funding">Funding</a>'
        "</main></body></html>"
    ),
    "https://example.org/eligibility": (
        "<html><body><main><p>You must be a Nigerian citizen.</p>"
        '<a href="/apply">Apply</a></main></body></html>'
    ),
    "https://example.org/funding": "<html><body><main><p>Tuition and stipend are covered.</p></main></body></html>",
    "https://example.org/apply": "<html><body><main><p>Applications close 13 October 2026.</p></main></body></html>",
    "https://example.org/other": (
        "<html><body><main><p>Another programme.</p>"
        '<a href="/eligibility">Eligibility</a></main></body></html>'
    ),
}


class _FakeFetcher:
    def fetch_text(self, url: str, **kwargs):
        return PAGES.get(url, "<html><body></body></html>"), _FakeFetch(url=url, html=PAGES.get(url, ""))


def _manifest() -> Manifest:
    return Manifest(
        corpus="test",
        target_intake_year=2027,
        sources=(
            SourceEntry(url="https://example.org/scholarship", name="Example Scholarship"),
            SourceEntry(url="https://example.org/other", name="Other Programme"),
        ),
    )


def test_url_key_ignores_fragment_query_and_trailing_slash() -> None:
    assert _url_key("https://Example.org/a/?x=1#top") == _url_key("https://example.org/a")


def test_shared_child_page_is_captured_once_and_attached_to_the_root(tmp_path) -> None:
    results = capture_manifest(
        _manifest(),
        output_dir=tmp_path,
        crawl_depth=3,
        delay_seconds=0,
        fetcher_factory=lambda source: _FakeFetcher(),
    )

    urls = [result.url for result in results]
    assert urls.count("https://example.org/eligibility") == 1

    eligibility = next(result for result in results if result.url.endswith("/eligibility"))
    assert eligibility.parent_url == "https://example.org/scholarship"


def test_grandchildren_are_attached_to_the_root_source(tmp_path) -> None:
    results = capture_manifest(
        _manifest(),
        output_dir=tmp_path,
        crawl_depth=3,
        delay_seconds=0,
        fetcher_factory=lambda source: _FakeFetcher(),
    )

    apply_page = next(result for result in results if result.url.endswith("/apply"))
    # Discovered from /eligibility, but grouped with the programme it belongs to.
    assert apply_page.parent_url == "https://example.org/scholarship"


def test_manifest_sources_are_not_recaptured_as_children(tmp_path) -> None:
    results = capture_manifest(
        _manifest(),
        output_dir=tmp_path,
        crawl_depth=3,
        delay_seconds=0,
        fetcher_factory=lambda source: _FakeFetcher(),
    )

    urls = [result.url for result in results]
    assert urls.count("https://example.org/scholarship") == 1
    assert urls.count("https://example.org/other") == 1


def test_crawl_depth_limits_the_number_of_extra_pages(tmp_path) -> None:
    results = capture_manifest(
        _manifest(),
        output_dir=tmp_path,
        crawl_depth=1,
        delay_seconds=0,
        fetcher_factory=lambda source: _FakeFetcher(),
    )

    # Two manifest pages, and one discovered page: the second source only links
    # to a page that was already captured.
    assert len(results) == 3
    assert [result.url for result in results].count("https://example.org/scholarship") == 1
