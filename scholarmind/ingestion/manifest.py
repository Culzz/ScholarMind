"""Source manifest loading and validation.

The manifest is the ingestion allowlist: a URL that is not listed is never
fetched. It also carries the trust tier and refresh cadence for each source, so
the scheduler can decide what to check and how often.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

VALID_SOURCE_TYPES = {
    "government",
    "university",
    "foundation",
    "ngo",
    "corporate",
    "multilateral",
    "intergovernmental",
}

VALID_TRUST_TIERS = {
    "official_primary",
    "official_secondary",
    "partner",
    "aggregator",
}


@dataclass(frozen=True)
class SourceEntry:
    """One allowlisted source."""

    url: str
    name: str
    provider_type: str = "other"
    trust_tier: str = "official_primary"
    cadence_hours: int = 168
    scope: tuple[str, ...] = ()
    level: str = "masters"
    notes: str = ""
    requires_render: bool = False
    fetch_policy: str = "direct"
    parent_url: str | None = None
    group: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "provider_type": self.provider_type,
            "trust_tier": self.trust_tier,
            "cadence_hours": self.cadence_hours,
            "scope": list(self.scope),
            "level": self.level,
            "notes": self.notes,
            "requires_render": self.requires_render,
            "fetch_policy": self.fetch_policy,
            "parent_url": self.parent_url,
            "group": self.group,
        }


@dataclass(frozen=True)
class Manifest:
    """A parsed source manifest."""

    corpus: str
    target_intake_year: int
    sources: tuple[SourceEntry, ...]
    discovery_hints: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[SourceEntry]:
        return iter(self.sources)

    def __len__(self) -> int:
        return len(self.sources)

    @property
    def urls(self) -> set[str]:
        return {source.url for source in self.sources}


def _parse_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise RuntimeError("PyYAML is required to read source manifests") from exc
    return yaml.safe_load(text) or {}


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a manifest file."""
    raw = _parse_yaml(Path(path).read_text(encoding="utf-8"))
    defaults = raw.get("defaults") or {}

    valid_fetch_policies = {"direct", "browser", "manual"}

    sources: list[SourceEntry] = []
    seen: set[str] = set()
    for item in raw.get("sources") or []:
        url = (item.get("url") or "").strip()
        if not url:
            raise ValueError("every manifest source requires a url")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"source url must be http(s): {url}")
        if url in seen:
            raise ValueError(f"duplicate source url in manifest: {url}")
        seen.add(url)

        provider_type = item.get("provider_type", "other")
        if provider_type not in VALID_SOURCE_TYPES:
            raise ValueError(f"unknown provider_type '{provider_type}' for {url}")

        trust_tier = item.get("trust_tier", defaults.get("trust_tier", "official_primary"))
        if trust_tier not in VALID_TRUST_TIERS:
            raise ValueError(f"unknown trust_tier '{trust_tier}' for {url}")

        cadence = int(item.get("cadence_hours", defaults.get("cadence_hours", 168)))
        if cadence < 1:
            raise ValueError(f"cadence_hours must be >= 1 for {url}")

        fetch_policy = item.get("fetch_policy", defaults.get("fetch_policy", "direct"))
        if fetch_policy not in valid_fetch_policies:
            raise ValueError(f"unknown fetch_policy '{fetch_policy}' for {url}")
        # A bot-blocked page can only be captured with the headless adapter,
        # so the flag falls back to the policy rather than being contradictory.
        requires_render = bool(item.get("requires_render", fetch_policy == "browser"))

        sources.append(
            SourceEntry(
                url=url,
                name=item.get("name") or url,
                provider_type=provider_type,
                trust_tier=trust_tier,
                cadence_hours=cadence,
                scope=tuple(item.get("scope") or ()),
                level=item.get("level", defaults.get("level", "masters")),
                notes=item.get("notes", ""),
                requires_render=requires_render,
                fetch_policy=fetch_policy,
                group=item.get("group"),
            )
        )

    return Manifest(
        corpus=raw.get("corpus", "unnamed"),
        target_intake_year=int(raw.get("target_intake_year", 2027)),
        sources=tuple(sources),
        discovery_hints=tuple(raw.get("discovery_hints") or ()),
        defaults=defaults,
    )


def due_sources(manifest: Manifest, last_checked: dict[str, Any]) -> list[SourceEntry]:
    """Return the sources whose refresh cadence has elapsed.

    ``last_checked`` maps a source URL to its last successful check timestamp.
    Sources never checked are always due, except ``manual`` policy entrants:
    those are unreachable from the fetcher's network (DNS, timeout or geo) and
    are entered by hand with provenance - scheduling them would only hammer a
    host that has already refused us.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    due: list[SourceEntry] = []
    for source in manifest.sources:
        if source.fetch_policy == "manual":
            continue
        checked = last_checked.get(source.url)
        if checked is None:
            due.append(source)
            continue
        if isinstance(checked, str):
            checked = datetime.fromisoformat(checked)
        elapsed_hours = (now - checked).total_seconds() / 3600
        if elapsed_hours >= source.cadence_hours:
            due.append(source)
    return due
