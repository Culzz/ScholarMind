"""Offline evaluation harness.

Runs a *system* (a retrieval + answering strategy) over a *split* of the gold
dataset and writes a ``results.json`` recording everything needed to reproduce the
run: dataset version, split, configuration, model ids, code commit and metrics.

Usage
-----
    python -m research.evaluation.harness.runner --experiment A --split dev \
        --dataset data/fixtures/eval/dev.jsonl

Rules
-----
* A result file without ``dataset_version``, ``split``, ``config``, ``model_id``
  and ``code_commit`` is invalid and must not be cited.
* Retrieval metrics and generation metrics are computed separately.
* Metrics are reported per question class; a single aggregate hides failing classes.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

DATASET_VERSION = "eval-v0"
EVAL_DIR = Path(__file__).resolve().parents[3]


@dataclass
class EvalItem:
    """One gold evaluation item."""

    id: str
    question: str
    question_type: str
    split: str
    difficulty: int = 1
    scholarship_slug: str = ""
    required_evidence: list[dict[str, Any]] = field(default_factory=list)
    gold_answer: str = ""
    acceptable_abstain: bool = False
    notes: str = ""


@dataclass
class ItemResult:
    """The outcome of running one item through one system."""

    item_id: str
    question_type: str
    retrieved_ids: list[str]
    required_ids: list[str]
    answer: str
    abstained: bool
    citation_ids: list[str]
    correct: bool | None = None
    notes: str = ""


def load_dataset(path: str | Path) -> list[EvalItem]:
    """Load a JSONL dataset of evaluation items."""
    items: list[EvalItem] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        items.append(
            EvalItem(
                id=raw["id"],
                question=raw["question"],
                question_type=raw["question_type"],
                split=raw.get("split", "dev"),
                difficulty=int(raw.get("difficulty", 1)),
                scholarship_slug=raw.get("scholarship_slug", ""),
                required_evidence=raw.get("required_evidence", []),
                gold_answer=raw.get("gold_answer", ""),
                acceptable_abstain=bool(raw.get("acceptable_abstain", False)),
                notes=raw.get("notes", ""),
            )
        )
    return items


def code_commit() -> str:
    """Best-effort git commit of the working tree."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(EVAL_DIR),
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # pragma: no cover - environment dependent
        return "unknown"


def bootstrap_ci(values: Sequence[float], *, iterations: int = 1000, seed: int = 13) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for a mean."""
    import random

    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means: list[float] = []
    n = len(values)
    for _ in range(iterations):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low = means[int(0.025 * iterations)]
    high = means[int(0.975 * iterations)]
    return (low, high)


def compute_metrics(results: Iterable[ItemResult]) -> dict[str, Any]:
    """Aggregate metrics overall and per question class."""
    results = list(results)
    if not results:
        return {"count": 0}

    recalls: list[float] = []
    by_type: dict[str, list[ItemResult]] = {}
    for result in results:
        required = set(result.required_ids)
        retrieved = result.retrieved_ids
        recalls.append(len(required.intersection(retrieved)) / len(required) if required else 0.0)
        by_type.setdefault(result.question_type, []).append(result)

    def summarise(group: list[ItemResult]) -> dict[str, Any]:
        group_recalls = [
            len(set(r.required_ids).intersection(r.retrieved_ids)) / len(set(r.required_ids))
            if r.required_ids
            else 0.0
            for r in group
        ]
        judged = [r for r in group if r.correct is not None]
        low, high = bootstrap_ci(group_recalls)
        return {
            "count": len(group),
            "recall_at_10": sum(group_recalls) / len(group_recalls) if group_recalls else 0.0,
            "recall_at_10_ci": [low, high],
            "correctness": (sum(1 for r in judged if r.correct) / len(judged)) if judged else None,
            "abstain_rate": sum(1 for r in group if r.abstained) / len(group),
        }

    return {
        "count": len(results),
        "recall_at_10": sum(recalls) / len(recalls),
        "by_question_type": {key: summarise(value) for key, value in sorted(by_type.items())},
    }


def write_results(
    *,
    experiment_id: str,
    system_id: str,
    dataset_path: str,
    split: str,
    metrics: dict[str, Any],
    config: dict[str, Any],
    model_id: str,
    embedding_model: str,
    prompt_version: str,
    output_root: Path,
) -> Path:
    """Write a reproducible results file and return its path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = output_root / experiment_id / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment_id": experiment_id,
        "system_id": system_id,
        "dataset_version": DATASET_VERSION,
        "dataset_path": dataset_path,
        "split": split,
        "config": config,
        "model_id": model_id,
        "embedding_model": embedding_model,
        "prompt_version": prompt_version,
        "code_commit": code_commit(),
        "started_at": stamp,
        "metrics": metrics,
    }
    path = out_dir / "results.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
