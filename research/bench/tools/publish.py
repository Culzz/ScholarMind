"""Build a ScholarBench-Africa release artifact.

The publisher reads the bench version directory, validates every item against
the documented schema, runs the redaction check, computes the SHA-256 of each
release file and writes:

* ``dist/bench-v1-<version>.jsonl`` — one merged release file, one record per
  line, each record tagged with the dataset version and the file it came from;
* ``dist/bench-v1-<version>.manifest.json`` — the release summary, including
  the per-file hashes and the item counts.

Usage
-----
    python research/bench/tools/publish.py --dry-run
    python research/bench/tools/publish.py

Exit codes: ``0`` on success, ``1`` when validation or redaction fails.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

BENCH_DIR = Path(__file__).resolve().parents[1]
RELEASE_DIR = BENCH_DIR / "bench-v1"
DIST_DIR = BENCH_DIR / "dist"

QUESTION_TYPES = frozenset(
    {"fact", "eligibility", "conflict", "prior_cycle", "insufficient", "adversarial"}
)
SPLITS = frozenset({"dev", "heldout"})
OVERALL_STATUSES = frozenset(
    {"eligible", "likely_eligible", "unknown", "not_eligible", "needs_review"}
)
RULE_VERDICTS = frozenset({"satisfied", "not_satisfied", "unknown", "needs_review"})
EDGE_CASES = frozenset(
    {
        "clearly_eligible",
        "one_mandatory_failure",
        "missing_profile_data",
        "ambiguous_wording",
        "conflicting_requirements",
        "cycle_specific",
    }
)
CHANGE_TYPES = frozenset(
    {
        "deadline",
        "opening_date",
        "funding",
        "eligibility",
        "document",
        "process",
        "contact",
        "cosmetic",
    }
)
ADVERSARIAL_FAMILIES = frozenset(
    {
        "injection_page",
        "expired_cycle",
        "near_duplicate",
        "conflicting_deadline",
        "funding_conditional",
        "fully_funded_trap",
        "empty_source",
    }
)
BLOCKING_FAMILIES = frozenset({"injection_page", "expired_cycle", "fully_funded_trap"})


@dataclass
class ValidationError:
    """One schema violation."""

    file: str
    record_id: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"file": self.file, "record_id": self.record_id, "detail": self.detail}


@dataclass
class ValidationResult:
    """The outcome of validating one release file."""

    file: str
    errors: list[ValidationError] = field(default_factory=list)
    records: int = 0


def _load_redact() -> Any:
    """Import the redaction module by path so the tool runs as a script."""
    path = Path(__file__).resolve().parent / "redact.py"
    spec = importlib.util.spec_from_file_location("bench_redact", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load redaction module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _require_keys(record: dict[str, Any], keys: Sequence[str], file_name: str, record_id: str) -> list[ValidationError]:
    missing = [key for key in keys if key not in record]
    if not missing:
        return []
    return [
        ValidationError(
            file=file_name, record_id=record_id, detail=f"missing key(s): {', '.join(sorted(missing))}"
        )
    ]


def _validate_question(record: dict[str, Any], file_name: str) -> list[ValidationError]:
    record_id = str(record.get("id", "<no id>"))
    errors = _require_keys(
        record,
        [
            "id",
            "question",
            "question_type",
            "split",
            "difficulty",
            "scholarship_slug",
            "required_evidence",
            "gold_answer",
            "acceptable_abstain",
            "verified",
            "notes",
        ],
        file_name,
        record_id,
    )
    if errors:
        return errors

    if record["question_type"] not in QUESTION_TYPES:
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="unknown question_type")
        )
    if record["split"] not in SPLITS:
        errors.append(ValidationError(file=file_name, record_id=record_id, detail="unknown split"))
    if not isinstance(record["difficulty"], int) or not 1 <= record["difficulty"] <= 5:
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="difficulty must be 1..5")
        )
    if not isinstance(record["acceptable_abstain"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="acceptable_abstain must be a bool")
        )
    if not isinstance(record["verified"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="verified must be a bool")
        )
    if not isinstance(record["required_evidence"], list):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="required_evidence must be a list")
        )
    else:
        for index, evidence in enumerate(record["required_evidence"]):
            if not isinstance(evidence, dict) or not {"claim", "source_hint", "snapshot_hint"} <= set(evidence):
                errors.append(
                    ValidationError(
                        file=file_name,
                        record_id=record_id,
                        detail=f"required_evidence[{index}] needs claim, source_hint and snapshot_hint",
                    )
                )
    return errors


def _validate_pair(record: dict[str, Any], file_name: str) -> list[ValidationError]:
    record_id = str(record.get("id", "<no id>"))
    errors = _require_keys(
        record,
        [
            "id",
            "scholarship_slug",
            "cycle_label",
            "profile",
            "gold_overall_status",
            "gold_rule_verdicts",
            "edge_case",
            "verified",
            "notes",
        ],
        file_name,
        record_id,
    )
    if errors:
        return errors

    if record["gold_overall_status"] not in OVERALL_STATUSES:
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="unknown gold_overall_status")
        )
    if record["edge_case"] not in EDGE_CASES:
        errors.append(ValidationError(file=file_name, record_id=record_id, detail="unknown edge_case"))
    if not isinstance(record["verified"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="verified must be a bool")
        )
    profile = record["profile"]
    if not isinstance(profile, dict):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="profile must be an object")
        )
    else:
        for key in ("nationality", "degree_level", "age", "field_of_study", "ielts", "degrees"):
            if key not in profile:
                errors.append(
                    ValidationError(file=file_name, record_id=record_id, detail=f"profile is missing {key}")
                )
        has_gpa = "gpa_value" in profile and "gpa_scale" in profile
        has_raw = "grade_scale_raw" in profile
        if has_gpa and has_raw:
            errors.append(
                ValidationError(
                    file=file_name,
                    record_id=record_id,
                    detail="profile must not carry both gpa_value/gpa_scale and grade_scale_raw",
                )
            )
    if not isinstance(record["gold_rule_verdicts"], list):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="gold_rule_verdicts must be a list")
        )
    else:
        for index, verdict in enumerate(record["gold_rule_verdicts"]):
            if not isinstance(verdict, dict) or not {"kind", "subject", "verdict", "reason"} <= set(verdict):
                errors.append(
                    ValidationError(
                        file=file_name,
                        record_id=record_id,
                        detail=f"gold_rule_verdicts[{index}] needs kind, subject, verdict and reason",
                    )
                )
            elif verdict["verdict"] not in RULE_VERDICTS:
                errors.append(
                    ValidationError(
                        file=file_name,
                        record_id=record_id,
                        detail=f"gold_rule_verdicts[{index}] has an unknown verdict",
                    )
                )
    return errors


def _validate_change(record: dict[str, Any], file_name: str) -> list[ValidationError]:
    record_id = str(record.get("id", "<no id>"))
    errors = _require_keys(
        record,
        [
            "id",
            "source_document_id",
            "field_name",
            "old_value",
            "new_value",
            "change_type",
            "expected_severity",
            "is_control",
            "verified",
            "notes",
        ],
        file_name,
        record_id,
    )
    if errors:
        return errors
    if record["change_type"] not in CHANGE_TYPES:
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="unknown change_type")
        )
    if not isinstance(record["is_control"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="is_control must be a bool")
        )
    if not isinstance(record["verified"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="verified must be a bool")
        )
    if record["is_control"] and record["old_value"] != record["new_value"]:
        errors.append(
            ValidationError(
                file=file_name,
                record_id=record_id,
                detail="a control pair must have identical old and new values",
            )
        )
    return errors


def _validate_adversarial(record: dict[str, Any], file_name: str) -> list[ValidationError]:
    record_id = str(record.get("id", "<no id>"))
    errors = _require_keys(
        record,
        [
            "id",
            "family",
            "input",
            "expected_behaviour",
            "automated_check",
            "blocks_release",
            "verified",
            "notes",
        ],
        file_name,
        record_id,
    )
    if errors:
        return errors
    if record["family"] not in ADVERSARIAL_FAMILIES:
        errors.append(ValidationError(file=file_name, record_id=record_id, detail="unknown family"))
    if not isinstance(record["blocks_release"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="blocks_release must be a bool")
        )
    if not isinstance(record["verified"], bool):
        errors.append(
            ValidationError(file=file_name, record_id=record_id, detail="verified must be a bool")
        )
    return errors


VALIDATORS: dict[str, Callable[[dict[str, Any], str], list[ValidationError]]] = {
    "questions.jsonl": _validate_question,
    "eligibility_pairs.jsonl": _validate_pair,
    "change_pairs.jsonl": _validate_change,
    "adversarial.jsonl": _validate_adversarial,
}


def validate_file(path: Path) -> ValidationResult:
    """Validate one release file against its schema."""
    validator = VALIDATORS[path.name]
    result = ValidationResult(file=path.name)
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        result.records += 1
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            result.errors.append(
                ValidationError(file=path.name, record_id=f"line {number}", detail=f"invalid JSON: {exc.msg}")
            )
            continue
        for error in validator(record, path.name):
            error.record_id = f"{error.record_id} (line {number})"
            result.errors.append(error)
    return result


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, as a hex digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_stem(version: str, release_line: str) -> str:
    """Build the artifact stem ``bench-v<line>-<version>``.

    ``version`` is the dataset version (``bench-v1.0``) and ``release_line``
    is the version line (``bench-v1``). The artifact is therefore
    ``bench-v1-1.0``.
    """
    line_number = release_line.rsplit("-", 1)[-1].lstrip("v") or "1"
    suffix = version.split("bench-v", 1)[1] if "bench-v" in version else version
    return f"bench-v{line_number}-{suffix}"


def build_release(release_dir: Path) -> dict[str, Any]:
    """Validate, redaction-check and assemble the release payload."""
    manifest_path = release_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    validations = [validate_file(release_dir / name) for name in VALIDATORS]
    errors = [error for result in validations for error in result.errors]

    redact = _load_redact()
    targets = [release_dir / name for name in VALIDATORS] + [manifest_path]
    redaction = redact.scan(targets)

    counts = {result.file: result.records for result in validations}
    declared = manifest.get("item_counts", {})
    count_errors = [
        ValidationError(
            file="manifest.json",
            record_id=counts_key,
            detail=f"declared {declared.get(counts_key)} items, file holds {counts.get(counts_key)}",
        )
        for counts_key in counts
        if counts_key in declared and declared[counts_key] != counts[counts_key]
    ]
    errors.extend(count_errors)

    version = str(manifest.get("version", "bench-v1"))
    release_line = str(manifest.get("release_line", "bench-v1"))
    stem = _artifact_stem(version, release_line)

    files_meta = []
    merged_lines: list[str] = []
    for name in VALIDATORS:
        path = release_dir / name
        files_meta.append(
            {
                "path": f"bench-v1/{name}",
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
                "items": counts[name],
            }
        )
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            record["dataset_version"] = version
            record["release_file"] = f"bench-v1/{name}"
            merged_lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))

    release_manifest = {
        "name": manifest.get("name", "ScholarBench-Africa"),
        "version": version,
        "release_line": release_line,
        "created": manifest.get("created"),
        "licence": manifest.get("licence"),
        "files": files_meta,
        "item_counts": counts,
        "class_distribution": manifest.get("class_distribution"),
        "splits": manifest.get("splits"),
        "annotation_status": manifest.get("annotation_status"),
        "verification_status": manifest.get("verification_status"),
        "content_hashes": {entry["path"]: "sha256:" + entry["sha256"] for entry in files_meta},
        "redaction": {
            "ok": redaction["ok"],
            "findings": len(redaction["findings"]),
        },
        "validation": {
            "ok": not errors,
            "errors": [error.to_dict() for error in errors],
        },
    }

    return {
        "stem": stem,
        "release_dir": release_dir,
        "dist_dir": DIST_DIR,
        "merged_lines": merged_lines,
        "release_manifest": release_manifest,
        "errors": errors,
        "redaction": redaction,
        "counts": counts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns 0 on success, 1 on validation or redaction failure."""
    parser = argparse.ArgumentParser(
        prog="publish.py", description="Build a ScholarBench-Africa release artifact."
    )
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=RELEASE_DIR,
        help="bench version directory to publish (default: %(default)s)",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=DIST_DIR,
        help="directory the artifact is written to (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report what would be written")
    args = parser.parse_args(argv)

    try:
        release = build_release(args.release_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    stem = release["stem"]
    data_path = args.dist_dir / f"{stem}.jsonl"
    manifest_path = args.dist_dir / f"{stem}.manifest.json"
    payload = "\n".join(release["merged_lines"]) + "\n"

    print(f"release line : {release['release_manifest']['release_line']}")
    print(f"version      : {release['release_manifest']['version']}")
    for name, count in sorted(release["counts"].items()):
        print(f"  {name}: {count} item(s)")
    print(f"merged file  : {data_path} ({len(release['merged_lines'])} line(s))")
    print(f"manifest file: {manifest_path}")

    for error in release["errors"]:
        print(f"  validation error: {error.file} {error.record_id}: {error.detail}", file=sys.stderr)
    for finding in release["redaction"]["findings"]:
        print(
            f"  redaction finding: [{finding['kind']}] {finding['file']} {finding['path']}: "
            f"{finding['detail']}",
            file=sys.stderr,
        )

    if release["errors"] or release["redaction"]["findings"]:
        print("release blocked: fix the findings above before publishing", file=sys.stderr)
        return 1

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    args.dist_dir.mkdir(parents=True, exist_ok=True)
    data_path.write_text(payload, encoding="utf-8", newline="\n")
    manifest_path.write_text(
        json.dumps(release["release_manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {data_path} ({len(payload.encode('utf-8'))} bytes)")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
