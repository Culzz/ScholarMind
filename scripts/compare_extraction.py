"""Compare extraction on the old tag-strip text and the new content text."""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholarmind.extraction.extract import extract_all  # noqa: E402
from scholarmind.ingestion.fetcher import _normalise_text  # noqa: E402


def old_normalise(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    if "<html" in text[:2000].lower() or "<!doctype html" in text[:2000].lower():
        text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<!--.*?-->", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;?", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def counts(text: str) -> collections.Counter:
    result = extract_all(text)
    return collections.Counter(fact.claim_type.value for fact in result.facts)


def main() -> int:
    old_total: collections.Counter = collections.Counter()
    new_total: collections.Counter = collections.Counter()
    old_only: list[tuple[str, collections.Counter]] = []

    for folder in sorted(p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir()):
        html_path = folder / "page.html"
        if not html_path.exists():
            continue
        raw = html_path.read_bytes()
        old_text = old_normalise(raw)
        new_text = _normalise_text(raw)
        old_counts = counts(old_text)
        new_counts = counts(new_text)
        old_total.update(old_counts)
        new_total.update(new_counts)
        if old_counts - new_counts:
            old_only.append((folder.name, old_counts - new_counts))

    print("claim type            old  new")
    for claim_type in sorted(set(old_total) | set(new_total)):
        print(f"{claim_type:<20} {old_total[claim_type]:>4} {new_total[claim_type]:>4}")

    print("\npages losing facts (old-only):")
    for name, diff in old_only:
        print(f"  {name}: {dict(diff)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
