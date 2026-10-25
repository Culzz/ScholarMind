"""Tests for the ingestion safety layer (SSRF protection)."""

from __future__ import annotations

import pytest

from scholarmind.ingestion.safety import (
    SafetyPolicy,
    UnsafeUrlError,
    build_policy,
    content_type_allowed,
    resolve_and_validate,
    validate_redirect,
)

POLICY = SafetyPolicy(allowed_hosts=frozenset({"example.org", "scholarship.gov.ng"}))


def test_non_http_scheme_is_rejected() -> None:
    for url in ("file:///etc/passwd", "ftp://example.org/x", "gopher://example.org"):
        with pytest.raises(UnsafeUrlError):
            resolve_and_validate(url, POLICY)


def test_host_not_in_allowlist_is_rejected() -> None:
    with pytest.raises(UnsafeUrlError):
        resolve_and_validate("https://evil.example.com/x", POLICY)


def test_loopback_host_is_rejected() -> None:
    policy = SafetyPolicy(allowed_hosts=frozenset({"localhost"}))
    with pytest.raises(UnsafeUrlError):
        resolve_and_validate("http://localhost:8080/admin", policy)


def test_metadata_endpoint_host_is_rejected() -> None:
    policy = SafetyPolicy(allowed_hosts=frozenset({"169.254.169.254"}))
    with pytest.raises(UnsafeUrlError):
        resolve_and_validate("http://169.254.169.254/latest/meta-data/", policy)


def test_disallowed_port_is_rejected() -> None:
    policy = SafetyPolicy(allowed_hosts=frozenset({"example.org"}), allowed_ports=frozenset({443}))
    with pytest.raises(UnsafeUrlError):
        resolve_and_validate("https://example.org:8443/x", policy)


def test_subdomain_of_allowed_host_is_accepted() -> None:
    # Host allow-listing is checked before any DNS lookup, so this is offline-safe.
    assert POLICY.host_allowed("apply.example.org")
    assert not POLICY.host_allowed("notexample.org")


def test_dns_resolution_failure_is_reported_as_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def _fail(*args: object, **kwargs: object) -> None:
        raise socket.gaierror("no network in tests")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(UnsafeUrlError):
        resolve_and_validate("https://example.org/x", POLICY)


def test_relative_redirect_stays_on_the_original_host() -> None:
    assert validate_redirect("/next-page", POLICY) == "/next-page"


def test_absolute_redirect_to_blocked_host_is_rejected() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_redirect("https://evil.example.com/", POLICY)


def test_content_type_allowlist() -> None:
    assert content_type_allowed("text/html; charset=utf-8", POLICY)
    # No PDF text extractor exists yet, so a PDF cannot become checkable
    # evidence; accepting it only stored unreadable bytes behind a citation.
    assert not content_type_allowed("application/pdf", POLICY)
    assert not content_type_allowed("application/octet-stream", POLICY)
    assert not content_type_allowed("text/html", SafetyPolicy(allowed_hosts=frozenset({"a.com"}), allowed_content_types=()))


def test_build_policy_collects_hosts() -> None:
    policy = build_policy(["https://a.org/x", "https://b.org/y"])
    assert policy.allowed_hosts == frozenset({"a.org", "b.org"})
    assert policy.host_allowed("a.org")
    assert not policy.host_allowed("c.org")


def test_blocked_hostnames_are_never_allowed() -> None:
    policy = SafetyPolicy(allowed_hosts=frozenset({"localhost"}))
    assert not policy.host_allowed("localhost")
    assert not policy.host_allowed("metadata.google.internal")
