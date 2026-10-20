"""HTTP client construction.

The concrete HTTP client lives in the application layer so the core package
stays free of third-party network libraries. Redirects are disabled here
because the fetcher validates every hop itself against the safety policy.
"""

from __future__ import annotations

from typing import Any


def build_http_client(
    *,
    user_agent: str = "ScholarMindBot/1.0",
    timeout_seconds: int = 20,
) -> Any:
    """Build an httpx client configured for safe, policy-checked fetching."""
    import httpx

    return httpx.Client(
        follow_redirects=False,
        timeout=timeout_seconds,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
            "Accept-Language": "en",
        },
    )
