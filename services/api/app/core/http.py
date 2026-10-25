"""HTTP client construction.

The concrete HTTP client lives in the application layer so the core package
stays free of third-party network libraries.

The client pins every connection to an address that the safety policy has
already validated. Handing a hostname to a normal HTTP library would resolve it
a second time, leaving a DNS-rebinding gap between the check and the request.
Redirects stay disabled in the fetcher, which validates each hop itself.
"""

from __future__ import annotations

from typing import Any

from scholarmind.ingestion.pinned_client import PinnedHTTPClient
from scholarmind.ingestion.safety import SafetyPolicy


def build_http_client(
    policy: SafetyPolicy,
    *,
    user_agent: str = "ScholarMindBot/1.0",
    timeout_seconds: int = 20,
) -> Any:
    """Build a policy-checked, address-pinned HTTP client."""
    return PinnedHTTPClient(
        policy,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
