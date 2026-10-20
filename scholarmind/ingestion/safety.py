"""Fetch safety: allowlisting and SSRF protection.

A scholarship fetcher is a server-side request maker pointed at URLs that came
from a manifest, but a manifest is still an input. These checks make it safe to
fetch a manifest-provided URL without opening the internal network:

1. The host must be in the allowlist.
2. The resolved IP must be a public address (private, loopback, link-local,
   CGNAT, and cloud metadata ranges are rejected).
3. The same checks are re-applied after every redirect.
4. Only http/https, a restricted port set, and a small set of content types are
   allowed; the response body is size-capped.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/pdf",
)

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "instance-data",
}


class UnsafeUrlError(Exception):
    """Raised when a URL fails the safety checks."""


@dataclass(frozen=True)
class SafetyPolicy:
    """Policy applied to every outbound fetch."""

    allowed_hosts: frozenset[str]
    allowed_ports: frozenset[int] = frozenset(ALLOWED_PORTS)
    allowed_content_types: tuple[str, ...] = ALLOWED_CONTENT_TYPES
    max_bytes: int = 5 * 1024 * 1024
    max_redirects: int = 3

    def host_allowed(self, host: str) -> bool:
        if not host:
            return False
        host = host.lower().strip(".")
        if host in BLOCKED_HOSTNAMES:
            return False
        if not self.allowed_hosts:
            return True
        return host in self.allowed_hosts or any(
            host.endswith("." + allowed) for allowed in self.allowed_hosts
        )


def _ip_is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True when an address is routable on the public internet."""
    if address.is_private or address.is_loopback or address.is_link_local:
        return False
    if address.is_multicast or address.is_reserved or address.is_unspecified:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        # Carrier-grade NAT (100.64/10) and benchmarking (198.18/15) are not public.
        if address in ipaddress.ip_network("100.64.0.0/10") or address in ipaddress.ip_network("198.18.0.0/15"):
            return False
    if isinstance(address, ipaddress.IPv6Address):
        if address in ipaddress.ip_network("fc00::/7"):
            return False
        if address.ipv4_mapped is not None:
            return _ip_is_public(address.ipv4_mapped)
    return True


def resolve_and_validate(url: str, policy: SafetyPolicy) -> list[str]:
    """Resolve a URL's host and confirm it is safe to request.

    Returns the resolved IP addresses. Raises :class:`UnsafeUrlError` when the
    URL is not allowed or resolves to a non-public address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeUrlError("url has no host")
    if not policy.host_allowed(parsed.hostname):
        raise UnsafeUrlError(f"host not in the allowlist: {parsed.hostname}")
    if parsed.port and parsed.port not in policy.allowed_ports:
        raise UnsafeUrlError(f"port not allowed: {parsed.port}")

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"host could not be resolved: {parsed.hostname}") from exc

    addresses: list[str] = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not _ip_is_public(address):
            raise UnsafeUrlError(f"host resolves to a non-public address: {address}")
        addresses.append(str(address))

    if not addresses:
        raise UnsafeUrlError(f"host resolved to no usable addresses: {parsed.hostname}")
    return addresses


def validate_redirect(location: str, policy: SafetyPolicy) -> str:
    """Validate a redirect target against the same policy as the original URL."""
    resolved = urlparse(location)
    if not resolved.scheme:
        # Relative redirect: it stays on the original (already validated) host.
        return location
    resolve_and_validate(location, policy)
    return location


def build_policy(allowed_urls: list[str], **overrides) -> SafetyPolicy:
    """Build a policy whose allowlist is the set of hosts in the manifest."""
    hosts = set()
    for url in allowed_urls:
        host = urlparse(url).hostname
        if host:
            hosts.add(host.lower())
    return SafetyPolicy(allowed_hosts=frozenset(hosts), **overrides)


def content_type_allowed(content_type: str, policy: SafetyPolicy) -> bool:
    """Check the response content type against the policy."""
    mime = content_type.split(";")[0].strip().lower()
    return mime in policy.allowed_content_types
