"""A standard-library HTTP client that connects to a validated address.

Checking a hostname and then handing the hostname to an HTTP library is a
time-of-check/time-of-use gap: the library resolves the name again, and a
DNS answer can change between the two lookups. This client closes the gap by
resolving once, validating every returned address, and then connecting to the
validated address while keeping the original hostname for the ``Host`` header
and for TLS SNI and certificate verification.

It uses only the standard library, so the core ingestion package stays free of
third-party network dependencies. Redirects are never followed here: the
fetcher validates each hop itself.
"""

from __future__ import annotations

import http.client
import socket
import ssl
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from scholarmind.ingestion.safety import SafetyPolicy, resolve_and_validate


@dataclass(frozen=True)
class PinnedResponse:
    """The parts of an HTTP response the fetcher uses."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    final_url: str


def _read_headers(response: http.client.HTTPResponse) -> dict[str, str]:
    return {key.lower(): value for key, value in response.getheaders()}


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection that dials a pre-validated address."""

    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_address = address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port), self.timeout
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection pinned to an address but verified for the hostname."""

    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class PinnedHTTPClient:
    """Fetch a URL over a connection pinned to its validated address."""

    def __init__(
        self,
        policy: SafetyPolicy,
        *,
        user_agent: str = "ScholarMindBot/1.0",
        timeout_seconds: float = 20,
        max_bytes: int | None = None,
    ) -> None:
        self.policy = policy
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes or policy.max_bytes

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> PinnedResponse:
        """GET a URL, raising :class:`UnsafeUrlError` when it is not allowed."""
        addresses = resolve_and_validate(url, self.policy)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        address = addresses[0]

        if parsed.scheme == "https":
            connection: http.client.HTTPConnection = _PinnedHTTPSConnection(
                host, address, port, self.timeout_seconds
            )
        else:
            connection = _PinnedHTTPConnection(host, address, port, self.timeout_seconds)

        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
            "Accept-Language": "en",
            "Host": host,
        }
        if headers:
            request_headers.update({key: value for key, value in headers.items()})

        try:
            connection.request("GET", path, headers=request_headers)
            response = connection.getresponse()
            content = response.read(self.max_bytes + 1)
            return PinnedResponse(
                status_code=response.status,
                headers=_read_headers(response),
                content=content,
                final_url=url,
            )
        finally:
            connection.close()
