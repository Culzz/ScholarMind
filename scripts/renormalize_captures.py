"""Re-extract page text from the HTML already captured on disk.

Improving the text extractor does not require refetching: every capture keeps
its raw ``page.html``. This rewrites each ``page.txt`` with the current
extractor and updates the character counts in ``capture.json`` and the capture
report, so the corpus builder reads the better text.

    python scripts/renormalize_captures.py --captures data/raw
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholarmind.ingestion.fetcher import _normalise_text  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report_path = args.captures / "capture_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    by_path = {}
    if report is not None:
        for entry in report.get("results", []):
            if entry.get("path"):
                by_path[str(Path(entry["path"]).resolve())] = entry

    changed = 0
    before_total = 0
    after_total = 0
    for folder in sorted(path for path in args.captures.iterdir() if path.is_dir()):
        html_path = folder / "page.html"
        if not html_path.exists():
            continue

        old_text = (folder / "page.txt").read_text(encoding="utf-8") if (folder / "page.txt").exists() else ""
        new_text = _normalise_text(html_path.read_bytes())
        before_total += len(old_text)
        after_total += len(new_text)

        if new_text == old_text:
            continue
        changed += 1

        if args.dry_run:
            continue

        (folder / "page.txt").write_text(new_text, encoding="utf-8")
        capture_path = folder / "capture.json"
        if capture_path.exists():
            data = json.loads(capture_path.read_text(encoding="utf-8"))
            data["chars"] = len(new_text)
            capture_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        entry = by_path.get(str(folder.resolve()))
        if entry is not None:
            entry["chars"] = len(new_text)

    if report is not None and not args.dry_run and changed:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"pages rewritten: {changed}")
    print(f"text characters: {before_total:,} -> {after_total:,}")
    if args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
