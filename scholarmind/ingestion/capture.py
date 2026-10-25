"""Corpus capture.

Captures the allowlisted sources to disk so the corpus can be built and
reviewed without a running database. Each capture records the raw bytes, the
normalised text, the content hash, the response metadata and any trust signals
raised during the fetch.

The capture never weakens TLS verification: a certificate problem is recorded
as a trust signal against the source, not worked around.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scholarmind.ingestion.fetcher import SafeFetcher
from scholarmind.ingestion.manifest import Manifest, SourceEntry, load_manifest
from scholarmind.ingestion.safety import build_policy
from scholarmind.ingestion.scam_signals import ScamSignal, collect_signals, detect_tls_anomaly

logger = logging.getLogger(__name__)

CAPTURE_DIR = Path("data/raw")

# Link text and paths that usually lead to the pages carrying the facts.
RELEVANT_PATH_TOKENS = (
    "scholar",
    "eligibility",
    "eligib",
    "funding",
    "award",
    "apply",
    "application",
    "requirement",
    "deadline",
    "programme",
    "program",
    "tuition",
    "stipend",
    "grant",
    "bursar",
    "fees",
)

MAX_CRAWL_PAGES = 6


def _same_site(url: str, base_url: str) -> bool:
    from urllib.parse import urlparse

    from scholarmind.ingestion.safety import registrable_domain

    host = urlparse(url).hostname
    base_host = urlparse(base_url).hostname
    if not host or not base_host:
        return False
    return registrable_domain(host) == registrable_domain(base_host)


def _relevant_links(html: str, base_url: str, *, limit: int = 12) -> list[str]:
    """Same-site links that look like they carry scholarship facts."""
    from urllib.parse import urljoin

    import re

    candidates: list[str] = []
    for match in re.finditer(r'href="([^"#]+)"', html):
        href = match.group(1).strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        target = urljoin(base_url, href)
        if not target.startswith("http"):
            continue
        if not _same_site(target, base_url):
            continue
        path = target.lower()
        if any(token in path for token in RELEVANT_PATH_TOKENS):
            candidates.append(target)

    seen: set[str] = set()
    ordered: list[str] = []
    for target in candidates:
        clean = target.split("?")[0].rstrip("/")
        if clean in seen:
            continue
        seen.add(clean)
        ordered.append(clean)
        if len(ordered) >= limit:
            break
    return ordered


@dataclass
class CaptureResult:
    """The outcome of capturing one source."""

    url: str
    name: str
    trust_tier: str
    ok: bool = False
    status_code: int | None = None
    content_hash: str = ""
    chars: int = 0
    error: str | None = None
    signals: list[ScamSignal] = field(default_factory=list)
    captured_at: str = ""
    path: str | None = None
    parent_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "trust_tier": self.trust_tier,
            "ok": self.ok,
            "status_code": self.status_code,
            "content_hash": self.content_hash,
            "chars": self.chars,
            "error": self.error,
            "signals": [signal.to_dict() for signal in self.signals],
            "captured_at": self.captured_at,
            "path": self.path,
            "parent_url": self.parent_url,
        }


def _slug(url: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "source").replace(".", "_")
    return f"{host}_{abs(hash(url)) % 10_000:04d}"


def capture_source(
    source: SourceEntry,
    *,
    output_dir: Path,
    fetcher: SafeFetcher,
) -> CaptureResult:
    """Capture one source to disk."""
    result = CaptureResult(
        url=source.url,
        name=source.name,
        trust_tier=source.trust_tier,
        captured_at=datetime.now(timezone.utc).isoformat(),
        parent_url=source.parent_url,
    )

    text, fetch = fetcher.fetch_text(source.url)
    result.status_code = fetch.status_code
    result.content_hash = fetch.content_hash
    result.error = fetch.error
    result.ok = fetch.ok

    if fetch.error:
        result.signals.extend(detect_tls_anomaly(fetch.error))
        result.signals.extend(collect_signals(url=source.url, text="", trust_tier=source.trust_tier))
        return result

    result.signals.extend(collect_signals(url=source.url, text=text, trust_tier=source.trust_tier))

    target = output_dir / _slug(source.url)
    target.mkdir(parents=True, exist_ok=True)
    (target / "page.html").write_bytes(fetch.content)
    (target / "page.txt").write_text(text, encoding="utf-8")
    (target / "capture.json").write_text(
        json.dumps(
            {
                "url": source.url,
                "final_url": fetch.final_url,
                "name": source.name,
                "trust_tier": source.trust_tier,
                "status_code": fetch.status_code,
                "content_hash": fetch.content_hash,
                "headers": fetch.headers,
                "captured_at": result.captured_at,
                "parent_url": source.parent_url,
                "signals": [signal.to_dict() for signal in result.signals],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result.path = str(target)
    result.chars = len(text)
    return result


def _url_key(url: str) -> str:
    """Identity of a page for de-duplication (fragment and query dropped)."""
    return url.split("#")[0].split("?")[0].rstrip("/").lower()


def capture_manifest(
    manifest: Manifest,
    *,
    output_dir: Path = CAPTURE_DIR,
    limit: int | None = None,
    delay_seconds: int = 5,
    crawl_depth: int = 0,
    fetcher_factory: Any = None,
) -> list[CaptureResult]:
    """Capture every source in a manifest.

    ``crawl_depth`` follows in-domain links that look fact-bearing (eligibility,
    funding, application, deadline pages), up to that many extra pages per
    source. Each URL is captured at most once across the whole run: the same
    page is often linked from several sources, and capturing it repeatedly
    creates duplicate snapshots and splits one programme into several awards.
    Every discovered page is recorded against the *root* source, so grouping
    later does not depend on how deep the link was found.
    """
    from collections import deque

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[CaptureResult] = []
    seen: set[str] = set()

    sources = list(manifest.sources)
    if limit:
        sources = sources[:limit]

    for source in sources:
        if _url_key(source.url) in seen:
            logger.info("skipping %s: already captured", source.url)
            continue
        seen.add(_url_key(source.url))

        policy = build_policy([source.url])
        if fetcher_factory is not None:
            fetcher = fetcher_factory(source)
        else:
            from app.core.http import build_http_client

            client = build_http_client(policy, user_agent="ScholarMindBot/1.0")

            if source.requires_render:
                from scholarmind.ingestion.browser import is_available, to_client

                if is_available():
                    client = to_client(source.url, user_agent="ScholarMindBot/1.0")
                    logger.info("rendering %s in a headless browser", source.url)
                else:
                    logger.warning(
                        "%s needs a rendered capture but no browser is available; "
                        "the page will be recorded as not captured.",
                        source.url,
                    )

            fetcher = SafeFetcher(
                policy,
                user_agent="ScholarMindBot/1.0",
                client=client,
                min_delay_seconds=delay_seconds,
            )

        result = capture_source(source, output_dir=output_dir, fetcher=fetcher)
        results.append(result)
        logger.info(
            "%s %s (%s)",
            "captured" if result.ok else "failed",
            source.url,
            result.error or result.status_code,
        )

        if not (result.ok and crawl_depth > 0):
            continue

        # Breadth-first over the source's own pages, newest links last.
        queue: deque[tuple[str, str]] = deque([(source.url, result.path or "")])
        discovered = 0
        while queue and discovered < crawl_depth:
            page_url, page_path = queue.popleft()
            if not page_path:
                continue
            html = (Path(page_path) / "page.html").read_text(encoding="utf-8", errors="replace")

            for link in _relevant_links(html, page_url):
                if discovered >= crawl_depth:
                    break
                key = _url_key(link)
                if key in seen:
                    continue
                seen.add(key)
                discovered += 1

                child = SourceEntry(
                    url=link,
                    name=f"{source.name} — {link.rsplit('/', 1)[-1][:48]}",
                    provider_type=source.provider_type,
                    trust_tier=source.trust_tier,
                    cadence_hours=source.cadence_hours,
                    scope=source.scope,
                    level=source.level,
                    notes=f"Discovered by following a link from {source.url}",
                    parent_url=source.url,
                )
                child_result = capture_source(child, output_dir=output_dir, fetcher=fetcher)
                results.append(child_result)
                logger.info(
                    "  %s %s",
                    "captured" if child_result.ok else "failed",
                    link,
                )
                if child_result.ok and child_result.path:
                    queue.append((child_result.url, child_result.path))
    return results


def write_report(results: list[CaptureResult], *, output_dir: Path = CAPTURE_DIR) -> Path:
    """Write the capture report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    captured = [result for result in results if result.ok]
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "captured": len(captured),
        "failed": len(results) - len(captured),
        "signals": sum(len(result.signals) for result in results),
        "results": [result.to_dict() for result in results],
    }
    path = output_dir / "capture_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m scholarmind.ingestion.capture``."""
    import argparse

    parser = argparse.ArgumentParser(description="Capture the allowlisted scholarship sources.")
    parser.add_argument("--manifest", default="data/manifests/nigeria_v1.yaml")
    parser.add_argument("--output", default=str(CAPTURE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=int, default=5)
    parser.add_argument(
        "--crawl-depth",
        type=int,
        default=0,
        help="Follow up to N in-domain fact-bearing links per source.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    manifest = load_manifest(args.manifest)
    results = capture_manifest(
        manifest,
        output_dir=Path(args.output),
        limit=args.limit,
        delay_seconds=args.delay,
        crawl_depth=args.crawl_depth,
    )
    report = write_report(results, output_dir=Path(args.output))
    captured = sum(1 for result in results if result.ok)
    print(f"captured {captured}/{len(results)} sources; report at {report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
