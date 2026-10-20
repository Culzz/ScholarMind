# ScholarMind — Evaluation Protocol

**Version:** 1.0 · Owner: research track · Companion to `PLAN.md` §9

This document defines how ScholarMind is measured. Numbers that appear in the portfolio write-up,
model card, or marketing must be reproducible from this protocol. **No metric ships without a
`results.json` produced by this harness.**

---

## 1. Principles

1. **Retrieval and generation are evaluated separately.** A high Recall@10 does not mean a correct answer.
2. **The abstention case is a first-class class.** A system that answers everything is not measured well by precision alone.
3. **Every item is bound to required evidence.** "Correct" is defined against evidence, not against prose similarity.
4. **Held-out data is used once per release.** Development items guide iteration; held-out items gate claims.
5. **Baselines are always present.** A result without a baseline is not a result.
6. **Cost and latency are reported.** Reliability gains that triple inference cost must be visible.
7. **Failures are published.** Error analysis is a deliverable, not an appendix.

---

## 2. Datasets

### 2.1 Gold question set (Experiment A)
- **Target size:** 200–300 items (dev 120–180, held-out 60–120).
- **Item schema:** `research/evaluation/schema/item.schema.json`; stored as JSONL under `data/fixtures/eval/`.
- **Item classes** (stratified, with a minimum per class recorded in `splits.yaml`):

| Class | `question_type` | Definition | Example shape | Min items |
|---|---|---|---|---|
| Exact fact | `fact` | One field, one official statement | "What is the closing date for the Chevening 2027 cycle?" | 40 |
| Multi-condition eligibility | `eligibility` | Several rules must hold | "Do I qualify for X given nationality + degree + field + age?" | 40 |
| Conflicting sources | `conflict` | Two official pages disagree | "Which deadline is correct when the funder page and university page differ?" | 20 |
| Prior cycle | `prior_cycle` | Question refers to a closed/earlier cycle | "What were the requirements for the 2026 cycle?" | 20 |
| Insufficient evidence | `insufficient` | Correct behaviour is to abstain | "Does X cover visa fees?" when no source states it | 40 |
| Adversarial / injection | `adversarial` | Source text contains instruction-like content | Injected "ignore previous instructions…" in a snapshot | 20 |

- Each item stores: `required_evidence` (claim + source hint + optional snapshot), `gold_answer`,
  `acceptable_abstain`, `difficulty`, and `scholarship_slug` for category-stratified reporting.
- **Annotation protocol:** two annotators label independently; disagreements adjudicated; inter-annotator
  agreement (Cohen's κ) reported for eligibility and conflict classes. Items are invalidated if the
  required evidence later changes — the dataset version tracks source snapshot hashes.

### 2.2 Eligibility pair set (Experiment B)
- Scholarship–profile pairs, ~120–200 pairs, from realistic synthetic-but-labelled profiles plus
  hand-crafted edge cases.
- Classes: clearly eligible; clearly ineligible on one mandatory rule; missing profile data →
  unknown; ambiguous wording → needs_review; conflicting requirements; cycle-specific differences.
- Gold labels per rule, not just per pair, so rule-level precision/recall is computable.

### 2.3 Change-replay set (Experiment C)
- Replay corpus of ≥ 60 before/after snapshot pairs, produced by editing real snapshots (deadline
  shifted, funding amount changed, rule added/removed, requirement wording edited) plus untouched
  control pairs.
- Real archived snapshots are used where available; synthetic edits are labelled as such.

### 2.4 Ranking relevance set (Experiment D)
- 40–60 profiles × 40–60 candidate scholarships with graded relevance labels (0–3) from the
  annotators, plus a documented procedure for handling ties.

---

## 3. Systems under comparison

| ID | System | Description |
|---|---|---|
| **A0** | Lexical baseline | Postgres FTS, top-k chunks, extractive answer (sentences) — no generation |
| **A1** | Dense baseline | pgvector cosine, top-k chunks, same extractive answer |
| **A2** | Hybrid | FTS + dense via RRF (k=60), extractive answer |
| **A3** | Hybrid + rerank | A2 + cross-encoder rerank on top 50 → top 20, extractive answer |
| **A4** | Hybrid + structured intelligence | A3 + eligibility engine + freshness filter + conflict handling, generated answer with validation |
| **B0** | LLM match score | Single prompt asking the model for a percentage match (the naive baseline) |
| **B1** | Rule engine | Explicit typed rules evaluated deterministically |
| **B2** | Hybrid eligibility | LLM-proposed rules → validated → rule engine (proposed vs. validated comparison) |
| **C0** | Naive diff | Any text difference = change |
| **C1** | Field-aware detector | Typed field extraction → diff → classification → severity |
| **D0** | Weighted ranking | Transparent weighted score (fixed weights v1) |
| **D1** | Weight sensitivity | D0 under perturbed weight vectors (sensitivity analysis, not a new model) |

---

## 4. Metrics

### 4.1 Retrieval
| Metric | Definition | Target reading |
|---|---|---|
| Recall@5 / Recall@10 | Fraction of `required_evidence` items present in top-k retrieved chunks | Higher is better |
| Precision@k | Fraction of retrieved chunks marked relevant by annotators | Diagnostic |
| MRR | Mean reciprocal rank of the first relevant chunk | Higher is better |
| nDCG@10 | Rank discount over graded relevance | Higher is better |
| Chunk coverage | Share of required-evidence spans fully contained in a retrieved chunk (not merely overlapping) | Detects chunking failures |

### 4.2 Answering
| Metric | Definition |
|---|---|
| Answer correctness | LLM-assisted strict match against gold, plus human review of a 20% sample; disagreements adjudicated |
| Citation precision | Share of cited chunks that actually support the associated claim (human/LLM-assisted + human-validated) |
| Citation completeness | Share of material factual claims with at least one supporting citation |
| Correct-abstain rate | On `insufficient` items: share where the system abstains |
| Wrong-answer rate | Share of `insufficient` items answered with a substantive claim (the worst failure) |
| Conflict surfacing rate | On `conflict` items: share where both conflicting values are surfaced |
| Hallucinated-fact rate | Share of answers containing a factual claim not supported by any retrieved evidence |
| Latency / cost | p50/p95 ms and USD per query |

### 4.3 Eligibility
| Metric | Definition |
|---|---|
| Rule-level precision/recall/F1 | Over (rule, verdict) pairs against gold |
| Overall accuracy | Correct overall label per (profile, cycle) |
| **False-positive eligibility rate** | Share of assessments labelled eligible that are not — headline metric |
| Correct-unknown rate | Share of unknown-required items labelled `unknown` |
| Needs-review recall | Share of genuinely ambiguous/conflicting items flagged `needs_review` |

### 4.4 Freshness
| Metric | Definition |
|---|---|
| Change detection precision/recall | Per change type |
| Exact-value accuracy | Extracted new deadline/funding value exactly matches the edited value |
| Detection latency | Hours between the edit (as recorded in the replay) and the change event |
| False-alarm rate | Change events raised on control (unedited) pairs |
| Human-verification rate | Share of critical changes that reached a human reviewer |

### 4.5 Ranking
| Metric | Definition |
|---|---|
| nDCG@10 / Recall@10 | Over the graded relevance labels |
| Weight stability | Rank correlation (Kendall's τ) between D0 and perturbed D1 rankings |
| Factor attribution | Contribution of each factor to the top-10 composition (sensitivity report) |

### 4.6 Reporting discipline
- Report per class and per scholarship category, never one aggregate number.
- Report confidence intervals (bootstrap, n=1000) for the headline metrics.
- Report the paired difference and its CI for system comparisons (A2 vs A3, B1 vs B0, etc.).
- Include cost and latency tables alongside quality tables.

---

## 5. Evaluation items — schema

```json
{
  "id": "q_0042",
  "question": "What is the application deadline for the X 2027 cycle?",
  "question_type": "fact",
  "split": "dev",
  "difficulty": 2,
  "scholarship_slug": "x-2027",
  "required_evidence": [
    {"claim": "The application deadline is 2027-03-15", "source_hint": "funder_page", "snapshot_hint": "2027-01-10"}
  ],
  "gold_answer": "2027-03-15",
  "acceptable_abstain": false,
  "notes": "Deadline was extended after this snapshot; item re-validated at dataset v2."
}
```

`acceptable_abstain: true` items count as correct only when the system abstains *and* states what is missing.

---

## 6. Harness layout

```
research/evaluation/
├── harness/
│   ├── runner.py          # system × split × dataset → results
│   ├── systems/           # a0_lexical.py a1_dense.py a2_hybrid.py a3_rerank.py a4_intelligent.py
│   ├── metrics/
│   │   ├── retrieval.py   # recall@k, mrr, ndcg, chunk coverage
│   │   ├── answering.py   # correctness, citation precision/completeness, abstention
│   │   ├── eligibility.py # rule-level + aggregate
│   │   ├── freshness.py   # detection P/R, latency, false alarms
│   │   └── ranking.py     # ndcg@k, kendall tau
│   ├── judge.py           # LLM-assisted grader (with human-validated calibration set)
│   ├── splits.py          # dataset loading, split integrity checks
│   └── report.py          # results.json + markdown tables + figures
├── schemas/item.schema.json
├── splits.yaml
└── calibration/           # judge calibration labels
```

**Reproducibility:** every run records `dataset_version`, `split`, `config`, `model_id`,
`embedding_model`, `code_commit`, `seed`, `started_at/finished_at`. A run without these fields is invalid.

**Judge discipline:** the LLM judge is used for answer correctness and citation support, but it is
calibrated against a human-labelled set; if judge-human agreement (κ) falls below 0.7, those metric
families are reported as human-scored only.

---

## 7. Experiment protocols

### Experiment A — Retrieval & answer quality
1. Load split, build query, run each system.
2. Compute retrieval metrics against `required_evidence`.
3. Generate answers with a fixed generation config (model, temperature 0, prompt version).
4. Validate citations; score correctness, abstention, conflict surfacing.
5. Output: comparison table, per-class breakdown, latency/cost table, failure examples (≥ 15 cases).

**Decision rule:** keep the reranker (A3) only if it improves nDCG@10 and answer correctness with a
CI excluding zero, and does not breach the latency budget (p95 ≤ 8 s end-to-end).

### Experiment B — Eligibility reasoning
1. For each (profile, cycle) pair, run B0, B1, B2.
2. Score rule-level verdicts and overall labels.
3. Report false-positive eligibility rate with CI, and unknown handling.
4. Report the extra engineering cost (rule authoring time per scholarship) — the honest cost of B1/B2.

**Decision rule:** the rule engine must show a materially lower false-positive rate than B0 at an
acceptable unknown rate; otherwise the "authoritative rules" thesis is not supported and must be revised.

### Experiment C — Temporal freshness
1. Replay snapshot pairs through C0 and C1.
2. Compute detection P/R per change type, exact-value accuracy, false-alarm rate on controls.
3. Simulate a refresh cadence (daily) to report worst-case detection latency.
4. Report limitations explicitly: a daily check cannot guarantee immediate detection; a failed fetch ≠ closure.

### Experiment D — Personalized ranking
1. Score all candidates per profile with D0.
2. Compute nDCG@10 / Recall@10 against graded labels.
3. Perturb weights ±20% (documented grid) → Kendall's τ stability, and change in top-10 composition.
4. Report a "why this rank" explanation trace for three illustrative profiles.

---

## 8. Ablations
Minimum ablations for the research release:
1. Remove conflict detection → measure conflict-surfacing and wrong-answer rate.
2. Remove citation validation → measure hallucinated-fact rate.
3. Remove eligibility engine from A4 (LLM-only answers) → measure false-positive eligibility in answers.
4. Remove freshness filter → measure expired-cycle answer rate.
5. Remove reranker → measure retrieval and end-to-end deltas.

---

## 9. Release gates

| Gate | Requirement |
|---|---|
| R2 (retrieval) | A0 and A2 reproduce from a clean checkout with the same dataset version; A2 ≥ A0 on Recall@10; failure analysis ≥ 15 cases |
| R3 (eligibility) | False-positive eligibility rate reported with CI for B1 vs B0; labelled set ≥ 120 pairs |
| R3 (freshness) | Change-detection P/R per type on the replay set; control false-alarm rate < 10% |
| R4 (web) | No user-scoped data leaks across accounts (integration test) |
| R6 (hardening) | Injectable/adversarial items handled per the injection defence spec |
| R7 (research) | All experiments reproducible; every published number traceable to a results file; limitations documented |

---

## 10. Known limitations of this protocol (to publish)
- The gold set is authored by the same person building the system — mitigated by annotator agreement
  where a second annotator is available, and by stating it plainly.
- The corpus is small (40–60 scholarships) and Nigeria-first; conclusions may not transfer to other
  regions, funders, or larger corpora.
- Synthetic snapshot edits approximate real page changes; real archive-based pairs are added where available.
- Answer correctness relies on a calibrated LLM judge plus human sampling; it is not fully automated.
- The refresh cadence bounds temporal claims: detection latency is reported as a distribution, not a guarantee.
