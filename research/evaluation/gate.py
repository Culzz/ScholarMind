"""CI regression gate for the evaluation metrics.

Reads the committed experiment results (``research/experiments/*/*/results.json``),
extracts the metrics gated in ``docs/EVALUATION.md`` section 18 - false-eligible
rate, citation precision, answer correctness and Recall@10 - compares them with
the committed thresholds in ``research/evaluation/thresholds.json``, prints a
markdown table and exits non-zero when a metric regresses.

Usage
-----
    python -m research.evaluation.gate
    python research/evaluation/gate.py --results research/experiments/A/<stamp>/results.json

Behaviour
---------
* No results file: the gate prints a "no results" message and exits ``0``. A
  repository without a committed baseline is not a failing repository.
* A metric that is not present in the results file is reported as
  "not reported" and does not fail the gate; only a measured value can
  regress.
* A regression is a measured value on the wrong side of its threshold. The
  gate does not apply bootstrap confidence intervals; a run whose interval
  straddles the threshold should be reviewed by a human (docs/EVALUATION.md
  section 18.2, step 4).

Threshold policy
----------------
**Thresholds may only be tightened on the dev split, and never relaxed to make
a pull request pass** (docs/EVALUATION.md section 18.4). Tightening - raising a
quality floor or lowering a rate ceiling - is allowed only when a run on the
dev split justifies the new value, and the pull request must include that run
and the metric-table diff.

Relaxing a threshold requires all of the following, and nothing less:

1. a **written justification in the pull-request description** explaining why
   the previous threshold was wrong (a changed metric definition, a gold
   relabelling that invalidated the basis, a model upgrade that shifted the
   scale);
2. approval from a reviewer other than the pull-request author;
3. a **re-baseline commit** - the new thresholds are committed together with a
   fresh full dev-split run whose ``results.json`` is archived as the new
   baseline;
4. an entry in the changelog naming the old value, the new value and the
   reason.

Held-out splits never set or validate a threshold, and the change itself is
gated: the pull request that changes a threshold must show that the previous
thresholds still pass on the previous baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_GLOB = REPO_ROOT / "research" / "experiments"
DEFAULT_THRESHOLDS = Path(__file__).resolve().parent / "thresholds.json"

# Candidate keys per gated metric, in lookup order.
METRIC_KEYS: dict[str, tuple[str, ...]] = {
    "false_eligible_rate": (
        "false_eligible_rate",
        "false_eligible",
        "false_eligible_ratio",
    ),
    "citation_precision": ("citation_precision",),
    "answer_correctness": ("answer_correctness", "correctness"),
    "recall_at_10": ("recall_at_10", "recall@10", "recall_at_10_macro"),
}

# Per-question-type key used for the macro average, when the aggregate is absent.
BY_TYPE_KEYS: dict[str, tuple[str, ...]] = {
    "answer_correctness": ("correctness", "answer_correctness"),
    "recall_at_10": ("recall_at_10",),
}


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON document, returning an empty mapping on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def find_results_files(root: Path) -> list[Path]:
    """All committed result files under ``root`` (``<experiment>/<stamp>/results.json``)."""
    if not root.exists():
        return []
    return sorted(root.glob("*/*/results.json"))


def latest_results_file(root: Path) -> Path | None:
    """The most recently written results file under ``root``."""
    files = find_results_files(root)
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _as_float(value: Any) -> float | None:
    """Coerce a metric value to a float, or ``None`` when it is not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _macro_average(payload: dict[str, Any], metric: str) -> float | None:
    """Macro-average a per-question-type metric when no aggregate is present."""
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return None
    by_type = metrics.get("by_question_type")
    if not isinstance(by_type, dict):
        return None
    keys = BY_TYPE_KEYS.get(metric)
    if not keys:
        return None
    values: list[float] = []
    for row in by_type.values():
        if not isinstance(row, dict):
            continue
        for key in keys:
            number = _as_float(row.get(key))
            if number is not None:
                values.append(number)
                break
    if not values:
        return None
    return sum(values) / len(values)


def extract_metric(payload: dict[str, Any], metric: str) -> float | None:
    """Extract one gated metric from a results payload."""
    metrics = payload.get("metrics")
    candidates: list[dict[str, Any]] = []
    if isinstance(metrics, dict):
        candidates.append(metrics)
    candidates.append(payload)
    for source in candidates:
        for key in METRIC_KEYS.get(metric, ()):
            number = _as_float(source.get(key))
            if number is not None:
                return number
    return _macro_average(payload, metric)


def check_metric(value: float, direction: str, threshold: float) -> bool:
    """True when the value satisfies the threshold."""
    if direction == "min":
        return value >= threshold
    if direction == "max":
        return value <= threshold
    raise ValueError(f"unsupported direction: {direction}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default=None,
        help="path to a specific results.json (default: the newest under research/experiments)",
    )
    parser.add_argument(
        "--results-root",
        default=str(DEFAULT_RESULTS_GLOB),
        help="directory searched for experiment results",
    )
    parser.add_argument(
        "--thresholds",
        default=str(DEFAULT_THRESHOLDS),
        help="path to the committed thresholds file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Compare the recorded metrics with the committed thresholds."""
    args = parse_args(argv)

    thresholds_path = Path(args.thresholds)
    if not thresholds_path.exists():
        print(f"thresholds file not found: {thresholds_path}", file=sys.stderr)
        return 2
    thresholds_doc = load_json(thresholds_path)
    metrics_config = thresholds_doc.get("metrics")
    if not isinstance(metrics_config, dict) or not metrics_config:
        print(f"no thresholds configured in {thresholds_path}", file=sys.stderr)
        return 2

    results_path: Path | None = None
    if args.results:
        candidate = Path(args.results)
        if not candidate.exists():
            print(f"results file not found: {candidate}", file=sys.stderr)
            return 2
        results_path = candidate
    else:
        results_path = latest_results_file(Path(args.results_root))

    if results_path is None:
        print("no results found: nothing to gate (no experiment results under research/experiments)")
        return 0

    payload = load_json(results_path)
    if not payload:
        print(f"no results found: {results_path} is empty or unreadable")
        return 0

    split = thresholds_doc.get("split")
    recorded_split = payload.get("split")
    print(f"results: {results_path}")
    print(f"split:   {recorded_split} (thresholds are set on '{split}')")
    print()
    print("| Metric | Value | Threshold | Status |")
    print("|---|---|---|---|")

    failures: list[str] = []
    for metric, config in metrics_config.items():
        if not isinstance(config, dict):
            continue
        direction = str(config.get("direction", "min"))
        threshold = _as_float(config.get("threshold"))
        value = extract_metric(payload, metric)
        if threshold is None:
            print(f"| {metric} | n/a | n/a | not configured |")
            continue
        if value is None:
            print(f"| {metric} | n/a | {threshold} | not reported |")
            continue
        passed = check_metric(value, direction, threshold)
        status = "pass" if passed else "FAIL"
        print(f"| {metric} | {value:.4f} | {direction} {threshold} | {status} |")
        if not passed:
            failures.append(
                f"{metric}: {value:.4f} breaches the threshold {direction} {threshold}"
            )

    print()
    if failures:
        print("regression detected:")
        for failure in failures:
            print(f"- {failure}")
        print(
            "A gated metric failing blocks the pull request (docs/EVALUATION.md 18.3). "
            "Thresholds may not be relaxed to make a pull request pass (18.4)."
        )
        return 1

    print("no regression against the committed thresholds")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
