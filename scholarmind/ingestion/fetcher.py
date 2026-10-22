"""Fetching official sources.

The fetcher is deliberately conservative: it honours a courtesy delay per host,
uses conditional requests so an unchanged page costs the source nothing, caps
the response size, and refuses to follow a redirect that the safety policy
rejects. It never raises on a network problem — a failed fetch is data (a stale
source), not an exception.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scholarmind.ingestion.safety import (
    SafetyPolicy,
    UnsafeUrlError,
    content_type_allowed,
    resolve_and_validate,
    validate_redirect,
)


@dataclass
class FetchResult:
    """The outcome of one fetch attempt."""

    url: str
    final_url: str
    status_code: int | None
    content: bytes = b""
    content_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    content_hash: str = ""
    not_modified: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and (self.status_code is not None and 200 <= self.status_code < 300)

    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def hash_content(content: bytes) -> str:
    """SHA-256 of the raw bytes (the snapshot identity)."""
    return hashlib.sha256(content).hexdigest()


def _normalise_text(content: bytes) -> str:
    """Best-effort text extraction for change detection and chunking.

    HTML is reduced to its readable content: navigation, footers, forms and
    scripts are dropped, because they otherwise become the most common
    sentences in the evidence index and crowd out the facts.
    """
    text = content.decode("utf-8", errors="replace")
    lowered = text[:2000].lower()
    if "<html" in lowered or "<!doctype html" in lowered or "<body" in lowered:
        from scholarmind.ingestion.text import html_to_text

        return html_to_text(text)
    return text.strip()


class SafeFetcher:
    """Fetches allowlisted URLs with SSRF protection and courtesy pacing."""

    def __init__(
        self,
        policy: SafetyPolicy,
        *,
        user_agent: str = "ScholarMindBot/1.0",
        timeout_seconds: int = 20,
        min_delay_seconds: int = 5,
        max_bytes: int | None = None,
        client: Any = None,
    ) -> None:
        self.policy = policy
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_delay_seconds = min_delay_seconds
        self.max_bytes = max_bytes or policy.max_bytes
        # The HTTP client is injected by the caller: the core package stays
        # free of third-party network libraries and remains trivially testable.
        self._client = client
        self._last_request_at: dict[str, float] = {}

    # -- internals --------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "SafeFetcher requires an injected HTTP client "
                "(see services/api/app/core/http.py:build_http_client)."
            )
        return self._client

    def _respect_courtesy_delay(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.min_delay_seconds:
                time.sleep(self.min_delay_seconds - elapsed)
        self._last_request_at[host] = time.monotonic()

    # -- public API -------------------------------------------------------

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Fetch a URL, returning a result object rather than raising."""
        result = FetchResult(url=url, final_url=url, status_code=None)

        try:
            resolve_and_validate(url, self.policy)
        except UnsafeUrlError as exc:
            result.error = f"unsafe_url: {exc}"
            return result

        current = url
        redirects = 0
        client = self._get_client()

        while True:
            host = current.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
            self._respect_courtesy_delay(host)
            headers: dict[str, str] = {}
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

            try:
                response = client.get(current, headers=headers)
            except Exception as exc:  # network failures are expected, not fatal
                result.error = f"fetch_failed: {type(exc).__name__}: {exc}"
                result.final_url = current
                return result

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if not location:
                    result.error = "redirect_without_location"
                    return result
                redirects += 1
                if redirects > self.policy.max_redirects:
                    result.error = "too_many_redirects"
                    return result
                try:
                    target = validate_redirect(location, self.policy)
                except UnsafeUrlError as exc:
                    result.error = f"unsafe_redirect: {exc}"
                    return result
                current = _join_url(current, target)
                continue

            result.status_code = response.status_code
            result.final_url = current
            result.content_type = response.headers.get("content-type", "")
            result.headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in ("etag", "last-modified", "content-type", "content-length")
            }

            if response.status_code == 304:
                result.not_modified = True
                return result

            if not content_type_allowed(result.content_type, self.policy):
                result.error = f"content_type_not_allowed: {result.content_type}"
                return result

            content = response.content
            if len(content) > self.max_bytes:
                result.error = f"response_too_large: {len(content)} bytes"
                return result

            result.content = content
            result.content_hash = hash_content(content)
            return result

    # -- helpers -----------------------------------------------------------

    def fetch_text(self, url: str, **kwargs: Any) -> tuple[str, FetchResult]:
        """Fetch and return normalised text alongside the raw result."""
        result = self.fetch(url, **kwargs)
        if not result.ok:
            return "", result
        return _normalise_text(result.content), result


def _join_url(base: str, location: str) -> str:
    if location.startswith("http://") or location.startswith("https://"):
        return location
    from urllib.parse import urljoin

    return urljoin(base, location)
