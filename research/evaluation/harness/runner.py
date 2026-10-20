"""Minimal evaluation-harness runner used by the CI evaluation smoke test.

The runner executes one *system* over one *split* of the benchmark dataset and
writes a reproducible ``results.json`` through
``research.evaluation.harness.core.write_results``.

The only system implemented here is a **lexical stub**: for every item it
returns the item's own ``required_evidence`` ids and no answer. It exists so
the harness plumbing (dataset loading, metric computation, results layout) is
exercised in CI without a database, a model provider or a network connection.
It is *not* a candidate system and its numbers must never be cited as a
system result.

Usage
-----
    python -m research.evaluation.harness.runner \
        --experiment A --split dev \
        --dataset research/bench/bench-v1/questions.jsonl \
        --limit 20
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct-script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research.evaluation.harness import core

SYSTEM_ID = "lexical-stub"
MODEL_ID = "none"
EMBEDDING_MODEL = "none"
PROMPT_VERSION = "none"


def evidence_ids(item: core.EvalItem) -> list[str]:
    """Stable identifiers for an item's required evidence.

    Benchmark items identify evidence by ``id`` or ``chunk_id`` when captured;
    pending items do not, so a deterministic synthetic id is derived from the
    item id and the position of the evidence entry.
    """
    ids: list[str] = []
    for index, evidence in enumerate(item.required_evidence):
        raw = evidence.get("id") or evidence.get("chunk_id")
        if raw:
            ids.append(str(raw))
        else:
            ids.append(f"{item.id}:ev{index}")
    return ids


def lexical_stub(item: core.EvalItem) -> core.ItemResult:
    """Run the lexical baseline over one item.

    The stub retrieves the item's required evidence ids and produces no answer,
    so the run is a plumbing check rather than a system measurement.
    """
    ids = evidence_ids(item)
    return core.ItemResult(
        item_id=item.id,
        question_type=item.question_type,
        retrieved_ids=ids,
        required_ids=ids,
        answer="",
        abstained=True,
        citation_ids=[],
        correct=None,
        notes="lexical stub: no answer produced",
    )


def markdown_table(metrics: dict[str, Any]) -> str:
    """Render the metric summary as a markdown table."""
    lines = [
        "| Metric | Value |",
        "|---|---|",
        f"| count | {metrics.get('count', 0)} |",
        f"| recall_at_10 | {_format(metrics.get('recall_at_10'))} |",
    ]
    by_type = metrics.get("by_question_type") or {}
    for question_type in sorted(by_type):
        row = by_type[question_type] or {}
        lines.append(
            f"| recall_at_10 ({question_type}) | {_format(row.get('recall_at_10'))} |"
        )
        lines.append(f"| abstain_rate ({question_type}) | {_format(row.get('abstain_rate'))} |")
    return "\n".join(lines)


def _format(value: Any) -> str:
    """Format a metric value for the table."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="A", help="experiment id, e.g. A")
    parser.add_argument("--split", default="dev", help="dataset split to evaluate")
    parser.add_argument(
        "--dataset",
        default="research/bench/bench-v1/questions.jsonl",
        help="path to the JSONL dataset",
    )
    parser.add_argument("--limit", type=int, default=20, help="maximum number of items")
    parser.add_argument(
        "--output-root",
        default=None,
        help="directory the experiment tree is written to (default research/experiments)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the harness over a split subset and write the results file."""
    args = parse_args(argv)

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = core.EVAL_DIR / dataset_path
    if not dataset_path.exists():
        print(f"dataset not found: {dataset_path}", file=sys.stderr)
        return 2

    items = core.load_dataset(dataset_path)
    items = [item for item in items if item.split == args.split]
    if args.limit is not None and args.limit >= 0:
        items = items[: args.limit]
    if not items:
        print(f"no items for split '{args.split}' in {dataset_path}", file=sys.stderr)
        return 2

    results = [lexical_stub(item) for item in items]
    metrics = core.compute_metrics(results)

    output_root = Path(args.output_root) if args.output_root else core.EVAL_DIR / "research" / "experiments"
    results_path = core.write_results(
        experiment_id=args.experiment,
        system_id=SYSTEM_ID,
        dataset_path=str(dataset_path),
        split=args.split,
        metrics=metrics,
        config={
            "runner": "research.evaluation.harness.runner",
            "system": SYSTEM_ID,
            "limit": args.limit,
            "offline": True,
        },
        model_id=MODEL_ID,
        embedding_model=EMBEDDING_MODEL,
        prompt_version=PROMPT_VERSION,
        output_root=output_root,
    )

    table = markdown_table(metrics)
    print(table)
    print()
    print(f"results: {results_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
