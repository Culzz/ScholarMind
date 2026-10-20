"""Transparent ranking.

Recommendations are a prioritisation aid, never a probability of success. The
score is a weighted sum of named factors, and every recommendation carries the
factor values and the weights used, so a student can see exactly why something
sits where it does and adjust the weights themselves.

Learning-to-rank is deliberately absent: it would need real relevance labels,
and a model trained on synthetic clicks would misrepresent what students want.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

DEFAULT_WEIGHTS: dict[str, float] = {
    "confirmed_eligibility": 0.30,
    "deadline_urgency": 0.20,
    "funding_fit": 0.20,
    "field_alignment": 0.10,
    "effort": 0.10,
    "source_freshness": 0.10,
}

WEIGHT_LABELS = {
    "confirmed_eligibility": "How much of the eligibility criteria you already meet",
    "deadline_urgency": "How soon the application closes",
    "funding_fit": "How well the funding matches what you need",
    "field_alignment": "How closely the field matches yours",
    "effort": "How much preparation effort it needs",
    "source_freshness": "How recently the official page was checked",
}

# Factors where a higher raw value is worse (they are inverted during scoring).
INVERTED_FACTORS = {"effort"}


@dataclass
class RankedOpportunity:
    """One scored opportunity with its explanation."""

    scholarship_id: str
    name: str
    score: float
    factors: dict[str, float] = field(default_factory=dict)
    weighted_factors: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    cycle_id: str | None = None
    deadline: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scholarship_id": self.scholarship_id,
            "name": self.name,
            "cycle_id": self.cycle_id,
            "deadline": self.deadline,
            "score": round(self.score, 4),
            "factors": {key: round(value, 4) for key, value in self.factors.items()},
            "weighted_factors": {key: round(value, 4) for key, value in self.weighted_factors.items()},
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "interpretation": (
                "Prioritisation score only - it is not a probability of receiving the award."
            ),
        }


def normalise_weights(weights: Mapping[str, float] | None = None) -> dict[str, float]:
    """Normalise the weights to sum to 1, keeping every known factor."""
    merged = dict(DEFAULT_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key in merged:
                merged[key] = max(0.0, float(value))
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {key: value / total for key, value in merged.items()}


def score_opportunity(
    *,
    scholarship_id: str,
    name: str,
    factors: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
    reasons: Sequence[str] = (),
    blockers: Sequence[str] = (),
    cycle_id: str | None = None,
    deadline: str | None = None,
) -> RankedOpportunity:
    """Score one opportunity.

    ``factors`` are raw values in 0..1, where 1 is always best (including
    effort, where 1 means "little effort").
    """
    normalised = normalise_weights(weights)
    raw = {key: max(0.0, min(1.0, float(factors.get(key, 0.0)))) for key in normalised}
    weighted = {key: raw[key] * normalised[key] for key in normalised}
    total = sum(weighted.values())
    return RankedOpportunity(
        scholarship_id=scholarship_id,
        name=name,
        score=total,
        factors=raw,
        weighted_factors=weighted,
        reasons=list(reasons),
        blockers=list(blockers),
        cycle_id=cycle_id,
        deadline=deadline,
    )


def rank_opportunities(
    opportunities: Sequence[RankedOpportunity],
    *,
    weights: Mapping[str, float] | None = None,
) -> list[RankedOpportunity]:
    """Order opportunities by score, with a stable tie-break on name."""
    normalised = normalise_weights(weights)
    ordered = sorted(opportunities, key=lambda item: (-item.score, item.name.lower()))
    for index, opportunity in enumerate(ordered):
        opportunity.weighted_factors = {
            key: opportunity.factors.get(key, 0.0) * normalised[key] for key in normalised
        }
        opportunity.score = sum(opportunity.weighted_factors.values())
    return ordered


def weight_sensitivity(
    opportunities: Sequence[RankedOpportunity],
    *,
    weights: Mapping[str, float] | None = None,
    perturbation: float = 0.2,
) -> dict[str, Any]:
    """How stable the ranking is when the weights are perturbed.

    The result reports the rank correlation between the base ranking and the
    ranking under each perturbed weight vector, plus how much the top ten
    composition changes. An unstable ranking is a signal that the ordering is
    an artefact of the weights rather than of the fit.
    """
    from itertools import product

    base = normalise_weights(weights)
    base_ranking = [item.scholarship_id for item in rank_opportunities(opportunities, weights=base)]

    keys = sorted(base)
    variants: list[dict[str, float]] = []
    for key in keys:
        for direction in (-perturbation, perturbation):
            variant = dict(base)
            variant[key] = max(0.0, base[key] + direction)
            variants.append(variant)

    correlations: list[float] = []
    composition_changes: list[float] = []
    for variant in variants:
        ranking = [item.scholarship_id for item in rank_opportunities(opportunities, weights=variant)]
        correlations.append(_kendall_tau(base_ranking, ranking))
        top_base = set(base_ranking[:10])
        top_variant = set(ranking[:10])
        union = top_base | top_variant
        composition_changes.append(len(top_base ^ top_variant) / len(union) if union else 0.0)

    return {
        "base_weights": base,
        "variants_tested": len(variants),
        "mean_kendall_tau": round(sum(correlations) / len(correlations), 4) if correlations else 1.0,
        "min_kendall_tau": round(min(correlations), 4) if correlations else 1.0,
        "mean_top10_churn": round(sum(composition_changes) / len(composition_changes), 4) if composition_changes else 0.0,
        "note": (
            "A low rank correlation under small weight changes means the ordering is "
            "sensitive to the weights and should be presented with the factor breakdown."
        ),
    }


def _kendall_tau(order_a: Sequence[str], order_b: Sequence[str]) -> float:
    """Kendall's tau between two orderings of the same items."""
    positions_a = {item: index for index, item in enumerate(order_a)}
    positions_b = {item: index for index, item in enumerate(order_b)}
    shared = [item for item in order_a if item in positions_b]
    n = len(shared)
    if n < 2:
        return 1.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            delta_a = positions_a[shared[i]] - positions_a[shared[j]]
            delta_b = positions_b[shared[i]] - positions_b[shared[j]]
            if delta_a * delta_b > 0:
                concordant += 1
            elif delta_a * delta_b < 0:
                discordant += 1
    total = n * (n - 1) / 2
    return (concordant - discordant) / total if total else 1.0


def describe_weights(weights: Mapping[str, float] | None = None) -> list[dict[str, Any]]:
    """A slider-friendly description of the current weights."""
    normalised = normalise_weights(weights)
    return [
        {
            "key": key,
            "label": WEIGHT_LABELS.get(key, key),
            "weight": round(normalised[key], 4),
        }
        for key in sorted(normalised)
    ]
