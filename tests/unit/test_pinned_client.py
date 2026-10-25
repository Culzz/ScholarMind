"""The fetcher must connect to the address it validated.

A hostname check followed by a normal HTTP request resolves the name twice, so a
DNS answer can change in between. These tests pin the connection to the
validated address and check that the non-standard ports are refused.
"""

from __future__ import annotations

import pytest

from scholarmind.ingestion import pinned_client
from scholarmind.ingestion.safety import ALLOWED_PORTS, SafetyPolicy, UnsafeUrlError, resolve_and_validate


def test_only_standard_web_ports_are_allowed() -> None:
    assert ALLOWED_PORTS == {80, 443}


@pytest.mark.parametrize("port", [8080, 8443, 6379, 5432])
def test_resolve_rejects_non_standard_ports(port: int) -> None:
    policy = SafetyPolicy(allowed_hosts=frozenset({"example.org"}))

    with pytest.raises(UnsafeUrlError, match="port not allowed"):
        resolve_and_validate(f"https://example.org:{port}/page", policy)


def test_client_connects_to_the_validated_address(monkeypatch) -> None:
    policy = SafetyPolicy(allowed_hosts=frozenset({"example.org"}))
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        pinned_client,
        "resolve_and_validate",
        lambda url, policy: ["203.0.113.9"],
    )

    class _Connection:
        def __init__(self, host, address, port, timeout):
            captured.update(host=host, address=address, port=port, timeout=timeout)

        def request(self, method, path, headers=None):
            captured.update(method=method, path=path, headers=headers)

        def getresponse(self):
            class _Response:
                status = 200

                def getheaders(self):
                    return [("Content-Type", "text/html")]

                def read(self, limit):
                    return b"<html>ok</html>"

            return _Response()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(pinned_client, "_PinnedHTTPSConnection", _Connection)
    client = pinned_client.PinnedHTTPClient(policy)
    response = client.get("https://example.org/page?q=1", headers={"If-None-Match": "abc"})

    assert response.status_code == 200
    assert captured["host"] == "example.org"
    assert captured["address"] == "203.0.113.9"
    assert captured["port"] == 443
    assert captured["path"] == "/page?q=1"
    assert captured["headers"]["Host"] == "example.org"
    assert captured["headers"]["If-None-Match"] == "abc"
    assert captured["closed"] is True
