"""Scam and trust signals.

Scholarship scams target exactly the audience this platform serves, so the
fetcher records cheap, high-signal warnings alongside every capture. These are
*signals*, not verdicts: they lower the effective trust tier and surface a
warning, and a human dismisses or confirms them in the review console.

Signals collected here:
  lookalike_domain    the host resembles a well-known funder's domain
  non_official_portal the page asks for a login/payment on a non-official host
  application_fee     an application fee is mentioned by a source that should not charge one
  no_contact_details  no email, phone or postal contact is present on the page
  contradicts_funder  the page contradicts the funder's own page on a key field
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3}[\s-]?\d{3,4}")
FEE_RE = re.compile(
    r"(application|registration|processing|service)\s+fees?\s*(?:of|is|are|:)?\s*"
    r"(?:USD|US\$|\$|NGN|Naira|GBP|EUR|€|£)?\s*[\d,]+",
    re.IGNORECASE,
)
PAYMENT_RE = re.compile(r"\b(pay|bank transfer|wire transfer|bitcoin|crypto)\b", re.IGNORECASE)
LOGIN_RE = re.compile(r"(log\s?in|sign\s?in|create\s+account|register\s+here|upload\s+documents)", re.IGNORECASE)

# Domains whose look-alikes are commonly used in scholarship fraud.
KNOWN_FUNDER_DOMAINS = (
    "chevening.com",
    "commonwealthscholarships.org",
    "daad.de",
    "fulbrightscholarships.org",
    "ptdf.gov.ng",
    "ndpc.gov.ng",
    "setd.ng",
)


@dataclass(frozen=True)
class ScamSignal:
    """One warning about a source."""

    signal_type: str
    severity: str
    detail: str
    detection_method: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "severity": self.severity,
            "detail": self.detail,
            "detection_method": self.detection_method,
        }


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "").lower()


def detect_lookalike_domain(url: str) -> list[ScamSignal]:
    """Flag hosts that imitate a known funder (typo-squat style)."""
    host = _host(url)
    if not host:
        return []
    signals: list[ScamSignal] = []
    for known in KNOWN_FUNDER_DOMAINS:
        if host == known:
            continue
        base = known.split(".")[0]
        if base in host and not host.endswith(known):
            signals.append(
                ScamSignal(
                    signal_type="lookalike_domain",
                    severity="high",
                    detail=(
                        f"'{host}' contains '{base}' but is not the official domain '{known}'. "
                        "Verify this site before entering personal details."
                    ),
                )
            )
    return signals


def detect_fee_and_payment(text: str, *, trusted: bool) -> list[ScamSignal]:
    """Flag application-fee language, except on sources that legitimately charge."""
    if trusted:
        return []
    signals: list[ScamSignal] = []
    match = FEE_RE.search(text)
    if match:
        signals.append(
            ScamSignal(
                signal_type="application_fee",
                severity="high",
                detail=(
                    f"This page mentions an application fee ('{match.group(0).strip()}'). "
                    "Legitimate scholarship fees are uncommon — verify with the funder."
                ),
            )
        )
    if PAYMENT_RE.search(text) and match:
        signals.append(
            ScamSignal(
                signal_type="payment_request",
                severity="high",
                detail="The page requests payment. Never pay a scholarship fee by direct transfer.",
            )
        )
    return signals


def detect_missing_contacts(text: str) -> list[ScamSignal]:
    """Flag pages with no contact details at all."""
    if EMAIL_RE.search(text) or PHONE_RE.search(text):
        return []
    return [
        ScamSignal(
            signal_type="no_contact_details",
            severity="medium",
            detail="No email address or phone number was found on this page.",
        )
    ]


def detect_gated_portal(url: str, text: str) -> list[ScamSignal]:
    """Flag pages that push a login on a host that is not a known portal."""
    if not LOGIN_RE.search(text):
        return []
    host = _host(url)
    if any(host.endswith(known) for known in KNOWN_FUNDER_DOMAINS):
        return []
    return [
        ScamSignal(
            signal_type="non_official_portal",
            severity="medium",
            detail=f"'{host}' asks you to sign in or upload documents but is not a known official portal.",
        )
    ]


def detect_tls_anomaly(error: str | None) -> list[ScamSignal]:
    """Flag a TLS or certificate problem with a source.

    Certificate problems are never worked around: the fetch fails, and the
    source is marked with a signal so a reviewer can decide what to do.
    """
    if not error:
        return []
    lowered = error.lower()
    if "certificate" not in lowered and "ssl" not in lowered and "tls" not in lowered:
        return []
    if "hostname mismatch" in lowered:
        return [
            ScamSignal(
                signal_type="tls_anomaly",
                severity="high",
                detail=(
                    "The site's certificate does not match its hostname. That can happen "
                    "after a domain change, but it can also indicate a look-alike site. "
                    "Verify the address before using it."
                ),
            )
        ]
    return [
        ScamSignal(
            signal_type="tls_anomaly",
            severity="medium",
            detail=f"TLS problem while fetching this source: {error[:160]}",
        )
    ]


def collect_signals(
    *,
    url: str,
    text: str,
    trust_tier: str,
    contradicted_fields: Iterable[str] = (),
) -> list[ScamSignal]:
    """Run every signal check against one captured page."""
    trusted = trust_tier in ("official_primary", "official_secondary")
    signals: list[ScamSignal] = []
    signals.extend(detect_lookalike_domain(url))
    signals.extend(detect_fee_and_payment(text, trusted=trusted))
    signals.extend(detect_missing_contacts(text))
    signals.extend(detect_gated_portal(url, text))

    contradicted = list(contradicted_fields)
    if contradicted:
        signals.append(
            ScamSignal(
                signal_type="contradicts_funder",
                severity="high",
                detail=(
                    "This page contradicts the funder's own page on: " + ", ".join(contradicted) + "."
                ),
            )
        )
    return signals


def effective_trust_tier(base_tier: str, signals: Iterable[ScamSignal]) -> str:
    """Reduce the trust tier when a high-severity signal is present.

    A high-severity signal demotes a source to ``aggregator`` until a human
    dismisses it, which prevents it from being cited as a confirmed fact.
    """
    signals = list(signals)
    if any(signal.severity == "high" for signal in signals):
        return "aggregator"
    if signals and base_tier == "official_primary":
        return "official_secondary"
    return base_tier


def summarise_signals(signals: Iterable[ScamSignal]) -> dict[str, Any]:
    """Counts by severity and type, for the admin console."""
    signals = list(signals)
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for signal in signals:
        by_severity[signal.severity] = by_severity.get(signal.severity, 0) + 1
        by_type[signal.signal_type] = by_type.get(signal.signal_type, 0) + 1
    return {
        "total": len(signals),
        "by_severity": by_severity,
        "by_type": by_type,
        "highest_severity": max((s.severity for s in signals), default=None, key=lambda v: ("low", "medium", "high").index(v)),
    }
