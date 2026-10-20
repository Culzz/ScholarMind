"""Redaction check for the ScholarBench-Africa release files.

The benchmark publishes questions, evidence *descriptions*, snapshot ids and
content hashes. It must never publish page bodies. This module scans the
release files and fails when any of the following is found:

* a field longer than :data:`MAX_FIELD_CHARS` characters;
* an evidence marker (``<<<EVIDENCE`` and friends) or a long verbatim run of
  at least :data:`VERBATIM_RUN_CHARS` consecutive characters, which is the
  shape of a copied page paragraph or an embedded blob;
* a key named ``raw_content``, ``extracted_text``, ``content`` or
  ``page_text`` outside the allowlist;
* a URL pointing at a domain that is not on the allowlist derived from
  ``data/manifests/nigeria_v1.yaml``;
* an e-mail address outside the reserved example domains.

Usage
-----
    python research/bench/tools/redact.py --check
    python research/bench/tools/redact.py --json

Exit codes: ``0`` clean, ``1`` findings present or a file could not be read.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

#: Hard cap on the length of any single string value in the release files.
MAX_FIELD_CHARS = 2000

#: A contiguous run of at least this many characters in one value is treated as
#: a possible verbatim copy of page text. Approved spans must be shorter.
VERBATIM_RUN_CHARS = 300

#: Markers that indicate an attempt to inline captured evidence.
EVIDENCE_MARKERS: tuple[str, ...] = (
    "<<<EVIDENCE",
    "<<<SNAPSHOT",
    "<<<SPAN",
    "<<<PAGE",
    "[BEGIN EVIDENCE",
    "[EVIDENCE]",
)

#: Keys that would carry raw captured content.
FORBIDDEN_KEYS = frozenset({"raw_content", "extracted_text", "content", "page_text"})

#: Key paths where a forbidden key name is tolerated. Empty by default: the
#: release files have no legitimate use for a content-bearing key.
ALLOWED_KEY_PATHS = frozenset()

#: Domains allowed to appear in a published URL. Mirrors the official domains
#: in ``data/manifests/nigeria_v1.yaml``.
ALLOWED_DOMAINS = frozenset(
    {
        "aas.net",
        "aku.edu.ng",
        "apply.chevening.com",
        "cam.ac.uk",
        "chevening.com",
        "commonwealthscholarships.org",
        "daad.de",
        "ed.ac.uk",
        "fulbrightscholarships.org",
        "gatesfoundation.org",
        "manchester.ac.uk",
        "mastercardfdn.org",
        "mrc.ukri.org",
        "ndpc.gov.ng",
        "nnpcgroup.com",
        "nuprc.gov.ng",
        "ox.ac.uk",
        "pearson.com",
        "ptdf.gov.ng",
        "setd.ng",
        "uct.ac.za",
        "unilag.edu.ng",
        "weforum.org",
        "wellsfargo.com",
        "wits.ac.za",
    }
)

#: Reserved domains, used by synthetic fixtures that must not look like a
#: real contact address.
ALLOWED_EMAIL_DOMAINS = frozenset({"example.com", "example.net", "example.org"})

_URL_RE = re.compile(r"https?://[^\s\)\]\}<>\"']+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Finding:
    """One redaction problem found in a release file."""

    kind: str
    file: str
    path: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "file": self.file,
            "path": self.path,
            "detail": self.detail,
        }


def _normalise(value: str) -> str:
    """Collapse whitespace so runs are measured on the visible text."""
    return " ".join(value.split())


def _host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def check_value(value: str, file_name: str, path: str) -> list[Finding]:
    """Apply the content checks to a single string value."""
    findings: list[Finding] = []

    if len(value) > MAX_FIELD_CHARS:
        findings.append(
            Finding(
                kind="oversized_field",
                file=file_name,
                path=path,
                detail=f"field is {len(value)} characters, limit is {MAX_FIELD_CHARS}",
            )
        )

    for marker in EVIDENCE_MARKERS:
        if marker in value:
            findings.append(
                Finding(
                    kind="evidence_marker",
                    file=file_name,
                    path=path,
                    detail=f"evidence marker {marker!r} present",
                )
            )
            break

    normalised = _normalise(value)
    if len(normalised) >= VERBATIM_RUN_CHARS:
        findings.append(
            Finding(
                kind="verbatim_run",
                file=file_name,
                path=path,
                detail=(
                    f"contiguous run of {len(normalised)} characters, limit is "
                    f"{VERBATIM_RUN_CHARS}"
                ),
            )
        )

    for match in _URL_RE.finditer(value):
        host = _host_of(match.group(0))
        if host not in ALLOWED_DOMAINS:
            findings.append(
                Finding(
                    kind="url_domain",
                    file=file_name,
                    path=path,
                    detail=f"URL host {host!r} is not on the allowlist",
                )
            )

    for match in _EMAIL_RE.finditer(value):
        domain = match.group(0).rsplit("@", 1)[-1].lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            findings.append(
                Finding(
                    kind="email_address",
                    file=file_name,
                    path=path,
                    detail="an e-mail address that is not on a reserved example domain",
                )
            )

    return findings


def check_node(node: Any, file_name: str, path: str) -> list[Finding]:
    """Walk a parsed JSON value and collect findings."""
    findings: list[Finding] = []

    if isinstance(node, str):
        findings.extend(check_value(node, file_name, path))
    elif isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_KEYS and child_path not in ALLOWED_KEY_PATHS:
                findings.append(
                    Finding(
                        kind="forbidden_key",
                        file=file_name,
                        path=child_path,
                        detail=f"key {key!r} may carry raw captured content",
                    )
                )
            findings.extend(check_node(value, file_name, child_path))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            findings.extend(check_node(value, file_name, f"{path}[{index}]"))

    return findings


def check_jsonl(path: Path) -> tuple[list[Finding], int]:
    """Scan one JSONL file. Returns findings and the number of records read."""
    findings: list[Finding] = []
    count = 0
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        count += 1
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    kind="invalid_json",
                    file=path.name,
                    path=f"line {number}",
                    detail=f"line is not valid JSON: {exc.msg}",
                )
            )
            continue
        findings.extend(check_node(record, path.name, f"line {number}"))
    return findings, count


def check_json(path: Path) -> tuple[list[Finding], int]:
    """Scan one JSON file. Returns findings and the number of top-level keys."""
    findings: list[Finding] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            [
                Finding(
                    kind="invalid_json",
                    file=path.name,
                    path="$",
                    detail=f"file is not valid JSON: {exc.msg}",
                )
            ],
            0,
        )
    findings.extend(check_node(document, path.name, "$"))
    return findings, len(document) if isinstance(document, dict) else 0


def default_targets(bench_dir: Path) -> list[Path]:
    """Return the release files that make up a bench version."""
    release_dir = bench_dir / "bench-v1"
    targets = sorted(release_dir.glob("*.jsonl"))
    manifest = release_dir / "manifest.json"
    if manifest.exists():
        targets.append(manifest)
    return targets


def scan(targets: Iterable[Path]) -> dict[str, Any]:
    """Scan the given files and return a report."""
    findings: list[Finding] = []
    scanned: list[dict[str, Any]] = []

    for target in targets:
        if not target.exists():
            findings.append(
                Finding(
                    kind="missing_file",
                    file=target.name,
                    path=str(target),
                    detail="release file is missing",
                )
            )
            continue
        if target.suffix == ".jsonl":
            file_findings, records = check_jsonl(target)
        else:
            file_findings, records = check_json(target)
        findings.extend(file_findings)
        scanned.append(
            {
                "file": target.name,
                "records": records,
                "bytes": target.stat().st_size,
                "findings": len(file_findings),
            }
        )

    return {
        "ok": not findings,
        "scanned": scanned,
        "findings": [finding.to_dict() for finding in findings],
        "limits": {
            "max_field_chars": MAX_FIELD_CHARS,
            "verbatim_run_chars": VERBATIM_RUN_CHARS,
            "forbidden_keys": sorted(FORBIDDEN_KEYS),
            "allowed_domains": sorted(ALLOWED_DOMAINS),
            "allowed_email_domains": sorted(ALLOWED_EMAIL_DOMAINS),
        },
    }


def _format_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    for entry in report["scanned"]:
        lines.append(
            f"scanned {entry['file']}: {entry['records']} record(s), "
            f"{entry['bytes']} bytes, {entry['findings']} finding(s)"
        )
    if report["findings"]:
        lines.append("")
        lines.append(f"{len(report['findings'])} finding(s):")
        for finding in report["findings"]:
            lines.append(
                f"  [{finding['kind']}] {finding['file']} {finding['path']}: {finding['detail']}"
            )
    else:
        lines.append("")
        lines.append("no redaction findings")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns 0 when the release files are clean, 1 otherwise."""
    bench_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        prog="redact.py", description="Check the bench release files for leaked page content."
    )
    parser.add_argument(
        "--bench-dir",
        type=Path,
        default=bench_dir,
        help="directory holding the bench version directories (default: %(default)s)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        action="append",
        default=None,
        help="scan this file instead of the default release files (repeatable)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="strict mode: fail the run if any finding is present",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    targets = args.path if args.path else default_targets(args.bench_dir)
    if not targets:
        print("no release files found to scan", file=sys.stderr)
        return 1

    report = scan(targets)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_report(report))

    if report["findings"]:
        return 1
    if args.check and not report["scanned"]:
        print("no files were scanned", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
