"""Headless rendering adapter.

Several of the highest-value sources (Chevening among them) render their
eligibility content in the browser: the static HTML contains navigation and
country lists but none of the requirements. A plain HTTP fetch therefore
captures a page that looks fine and contains no facts.

This module provides an optional renderer built on Playwright. It is used only
for sources the manifest marks as ``requires_render: true``, it is never
required for the pipeline to run, and its absence is reported rather than
hidden.

Rendering is done politely: one page at a time, with the same user agent as
the direct fetcher, and no interaction beyond loading the URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 30_000


@dataclass
class RenderResult:
    """The outcome of rendering a page."""

    url: str
    final_url: str
    html: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.html)


def is_available() -> bool:
    """Whether a headless browser can be used in this environment."""
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return True


def render(
    url: str,
    *,
    user_agent: str = "ScholarMindBot/1.0",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    wait_selector: str | None = None,
) -> RenderResult:
    """Render a page and return its HTML.

    Returns a result with ``error`` set when no browser is available, so the
    caller can record the page as "not captured" rather than pretending it was.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on the environment
        return RenderResult(
            url=url,
            final_url=url,
            html="",
            error=f"renderer_unavailable: {type(exc).__name__}",
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=user_agent)
                page = context.new_page()
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception:
                        logger.info("selector %s never appeared on %s", wait_selector, url)
                html = page.content()
                final_url = page.url
            finally:
                browser.close()
        return RenderResult(url=url, final_url=final_url, html=html)
    except Exception as exc:  # pragma: no cover - depends on the environment
        return RenderResult(url=url, final_url=url, html="", error=f"render_failed: {type(exc).__name__}: {exc}")


def to_client(url: str, *, user_agent: str = "ScholarMindBot/1.0") -> Any:
    """A duck-typed client that renders instead of fetching.

    It exposes the small interface :class:`~scholarmind.ingestion.fetcher.SafeFetcher`
    expects (``get(url, headers=...)`` returning an object with ``status_code``,
    ``headers``, ``content`` and ``content_type``), so the pipeline is
    unchanged for rendered pages.
    """
    import httpx

    class _RenderedResponse:
        def __init__(self, status_code: int, headers: dict[str, str], content: bytes) -> None:
            self.status_code = status_code
            self.headers = headers
            self.content = content
            self.text = content.decode("utf-8", errors="replace")

    class RenderClient:
        """A client that renders pages with a headless browser."""

        def get(self, url: str, headers: dict[str, str] | None = None) -> Any:
            result = render(url, user_agent=user_agent)
            if not result.ok:
                return httpx.Response(
                    status_code=599,
                    headers={"content-type": "text/plain", "x-render-error": (result.error or "")[:200]},
                    content=b"",
                )
            return _RenderedResponse(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=result.html.encode("utf-8"),
            )

        def close(self) -> None:
            return None

    return RenderClient()
