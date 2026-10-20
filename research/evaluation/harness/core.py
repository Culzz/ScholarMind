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

# Number of equal-width confidence bins used for calibration analysis (docs/EVALUATION.md §13).
CALIBRATION_BINS = 5

# Judge agreement floor: below this kappa the LLM judge is demoted and the affected
# metric families are human-scored only (docs/EVALUATION.md §15).
JUDGE_KAPPA_THRESHOLD = 0.7

# USD per 1M tokens. Overridable per call to ``cost_report`` via ``pricing``.
DEFAULT_PRICING = {"input": 0.50, "output": 1.50, "embedding": 0.02}

MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "embedding": 0.02},
    "gpt-4o": {"input": 2.50, "output": 10.00, "embedding": 0.05},
    "text-embedding-3-small": {"input": 0.00, "output": 0.00, "embedding": 0.02},
    "text-embedding-3-large": {"input": 0.00, "output": 0.00, "embedding": 0.13},
}


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


# ---------------------------------------------------------------------------
# Calibration and reliability (docs/EVALUATION.md §13)
# ---------------------------------------------------------------------------


def bin_confidence(confidence: float, bins: int = CALIBRATION_BINS) -> int:
    """Map a 0..1 confidence to an equal-width calibration bin index.

    The bin index is in ``0 .. bins-1``. The top edge belongs to the last
    bin, so a confidence of ``1.0`` lands in ``bins-1`` rather than
    overflowing. Values outside ``0..1`` are clamped rather than rejected:
    a mis-calibrated extractor should be measured, not crash the harness.
    """
    if bins < 1:
        raise ValueError("bins must be >= 1")
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        value = 0.0
    value = min(1.0, max(0.0, value))
    index = int(value * bins)
    return min(bins - 1, max(0, index))


def calibration_curve(
    samples: Iterable[tuple[float, bool]],
    bins: int = CALIBRATION_BINS,
) -> dict[str, Any]:
    """Build a reliability curve over (confidence, correct) samples.

    ``samples`` is an iterable of ``(confidence, correct_bool)`` pairs — one
    per human-verified extracted fact. Facts are binned by confidence into
    equal-width bins; for each bin the observed precision is compared with the
    mean confidence of the bin. The expected calibration error (ECE) is the
    count-weighted mean absolute gap between the two.

    Returns a dict with the per-bin rows (``bin_index``, ``lower``, ``upper``,
    ``count``, ``precision``, ``mean_confidence``) and the overall
    ``expected_calibration_error``. Bins with no verified facts are omitted
    from the curve rather than plotted as zero precision.
    """
    if bins < 1:
        raise ValueError("bins must be >= 1")

    buckets: list[dict[str, Any]] = []
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        buckets.append(
            {
                "bin_index": index,
                "lower": lower,
                "upper": upper,
                "count": 0,
                "verified": 0,
                "correct": 0,
                "confidence_sum": 0.0,
                "precision": None,
                "mean_confidence": None,
            }
        )

    total = 0
    for confidence, correct in samples:
        bucket = buckets[bin_confidence(confidence, bins)]
        bucket["count"] += 1
        bucket["confidence_sum"] += float(confidence)
        total += 1
        if correct:
            bucket["correct"] += 1

    ece = 0.0
    curve: list[dict[str, Any]] = []
    for bucket in buckets:
        verified = bucket["count"]
        if verified:
            precision = bucket["correct"] / verified
            mean_confidence = bucket["confidence_sum"] / verified
            ece += (verified / total) * abs(precision - mean_confidence)
        else:
            precision = None
            mean_confidence = None
        curve.append(
            {
                "bin_index": bucket["bin_index"],
                "lower": bucket["lower"],
                "upper": bucket["upper"],
                "count": verified,
                "precision": precision,
                "mean_confidence": mean_confidence,
            }
        )

    return {
        "bins": curve,
        "count": total,
        "expected_calibration_error": ece if total else 0.0,
        "ece": ece if total else 0.0,
    }


def brier_score(samples: Iterable[tuple[float, bool]]) -> float:
    """Brier score of a set of (confidence, correct_bool) samples.

    Mean of ``(confidence - outcome) ** 2`` over all samples. Lower is
    better; 0.25 is the score of a constant 0.5 forecast.
    """
    total = 0
    squared = 0.0
    for confidence, correct in samples:
        outcome = 1.0 if correct else 0.0
        squared += (float(confidence) - outcome) ** 2
        total += 1
    if not total:
        return 0.0
    return squared / total


# ---------------------------------------------------------------------------
# LLM-judge validation (docs/EVALUATION.md §15)
# ---------------------------------------------------------------------------


def judge_agreement(
    labels: Iterable[tuple[str, str]],
    *,
    kappa_threshold: float = JUDGE_KAPPA_THRESHOLD,
) -> dict[str, Any]:
    """Cohen's kappa between human labels and judge labels.

    ``labels`` is an iterable of ``(human_label, judge_label)`` pairs, e.g.
    ``("supported", "supported")``. Returns the kappa, the per-class counts
    (a confusion matrix), per-class F1 for the human label, and a ``demoted``
    flag that is set when kappa falls below ``kappa_threshold`` — at which
    point the judge may not be used as the primary verifier and the dependent
    metric families are human-scored only.
    """
    pairs = [(str(human), str(judge)) for human, judge in labels]
    classes = sorted({label for pair in pairs for label in pair})

    matrix: dict[str, dict[str, int]] = {
        human: {judge: 0 for judge in classes} for human in classes
    }
    human_counts: dict[str, int] = {name: 0 for name in classes}
    judge_counts: dict[str, int] = {name: 0 for name in classes}
    agreements = 0

    for human, judge in pairs:
        matrix[human][judge] += 1
        human_counts[human] += 1
        judge_counts[judge] += 1
        if human == judge:
            agreements += 1

    total = len(pairs)
    if not total:
        return {
            "count": 0,
            "kappa": 0.0,
            "demoted": True,
            "kappa_threshold": kappa_threshold,
            "per_class_counts": matrix,
            "per_class_f1": {name: None for name in classes},
        }

    observed = agreements / total
    expected = sum(
        (human_counts[name] / total) * (judge_counts[name] / total) for name in classes
    )
    if expected >= 1.0:
        kappa = 1.0 if observed >= 1.0 else 0.0
    else:
        kappa = (observed - expected) / (1.0 - expected)

    per_class_f1: dict[str, float | None] = {}
    for name in classes:
        true_positive = matrix[name][name]
        false_positive = sum(
            matrix[other][name] for other in classes if other != name
        )
        false_negative = sum(
            matrix[name][other] for other in classes if other != name
        )
        denominator = 2 * true_positive + false_positive + false_negative
        per_class_f1[name] = (2 * true_positive / denominator) if denominator else None

    return {
        "count": total,
        "kappa": kappa,
        "observed_agreement": observed,
        "expected_agreement": expected,
        "demoted": kappa < kappa_threshold,
        "kappa_threshold": kappa_threshold,
        "per_class_counts": matrix,
        "per_class_f1": per_class_f1,
        "human_label_counts": human_counts,
        "judge_label_counts": judge_counts,
    }


# ---------------------------------------------------------------------------
# Cost and latency reporting (docs/EVALUATION.md §16)
# ---------------------------------------------------------------------------


def _percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile of a sequence of floats."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * min(1.0, max(0.0, q))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _pricing_for(model: str, pricing: dict[str, dict[str, float]] | None) -> dict[str, float]:
    """Price sheet for a model, falling back to the default rates."""
    table = pricing if pricing is not None else MODEL_PRICING_USD_PER_MTOK
    rates = table.get(model)
    if rates is None:
        rates = DEFAULT_PRICING
    return {
        "input": float(rates.get("input", DEFAULT_PRICING["input"])),
        "output": float(rates.get("output", DEFAULT_PRICING["output"])),
        "embedding": float(rates.get("embedding", DEFAULT_PRICING["embedding"])),
    }


def _summarise_group(
    records: list[dict[str, Any]],
    rates_by_model: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Aggregate one configuration's records into cost, latency and counts."""
    total_cost = 0.0
    abstention_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    embedding_tokens = 0
    latencies: list[float] = []
    correct_count = 0
    judged = 0
    abstained = 0

    for record in records:
        rates = rates_by_model.get(str(record.get("model", "")), DEFAULT_PRICING)
        model_input = int(record.get("input_tokens", 0) or 0)
        model_output = int(record.get("output_tokens", 0) or 0)
        model_embedding = int(record.get("embedding_tokens", 0) or 0)
        input_tokens += model_input
        output_tokens += model_output
        embedding_tokens += model_embedding
        record_cost = (
            model_input * rates["input"]
            + model_output * rates["output"]
            + model_embedding * rates["embedding"]
        ) / 1_000_000.0
        total_cost += record_cost
        latencies.append(float(record.get("latency_ms", 0.0) or 0.0))
        correct = record.get("correct")
        if correct is not None:
            judged += 1
            if correct:
                correct_count += 1
        if record.get("abstained"):
            abstained += 1
            abstention_cost += record_cost

    queries = len(records)
    return {
        "queries": queries,
        "cost_usd": total_cost,
        "cost_per_query_usd": total_cost / queries if queries else 0.0,
        "cost_per_correct_answer_usd": (
            total_cost / correct_count if correct_count else None
        ),
        "cost_per_abstention_usd": abstention_cost / abstained if abstained else None,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "mean": (sum(latencies) / len(latencies)) if latencies else 0.0,
        },
        "tokens": {
            "input": input_tokens,
            "output": output_tokens,
            "embedding": embedding_tokens,
        },
        "counts": {
            "queries": queries,
            "judged": judged,
            "correct": correct_count,
            "abstained": abstained,
        },
    }


def cost_report(
    records: Iterable[dict[str, Any]],
    *,
    pricing: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Cost and latency report over per-query call records.

    Each record is a dict with the keys ``model``, ``input_tokens``,
    ``output_tokens``, ``embedding_tokens``, ``latency_ms``, ``correct``
    (``bool`` or ``None`` when unjudged) and ``abstained`` (``bool``). An
    optional ``config`` key names the configuration; records are grouped by
    ``config`` when present and by ``model`` otherwise.

    Returns the overall totals and the per-configuration averages:
    ``cost_per_query_usd``, ``cost_per_correct_answer_usd``,
    ``cost_per_abstention_usd``, p50/p95/p99 latency and the counts. The price
    sheet used is recorded so old reports stay interpretable.
    """
    rows = [dict(record) for record in records]
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in rows:
        key = str(record.get("config") or record.get("model") or "unknown")
        groups.setdefault(key, []).append(record)

    rates_by_model = {
        str(record.get("model", "")): _pricing_for(str(record.get("model", "")), pricing)
        for record in rows
    }

    by_configuration = {
        key: _summarise_group(group, rates_by_model) for key, group in sorted(groups.items())
    }

    overall = _summarise_group(rows, rates_by_model)
    overall["by_configuration"] = by_configuration
    overall["pricing_usd_per_mtok"] = {
        model: rates for model, rates in sorted(rates_by_model.items())
    }

    return {
        "totals": overall,
        "by_configuration": by_configuration,
    }
