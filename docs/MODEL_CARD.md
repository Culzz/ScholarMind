# ScholarMind — System & Model Card

**Version:** 1.0 (template; final values filled at the research release, R7)
**Status:** pre-release — figures below are placeholders and MUST be replaced with measured values
before any external publication.

---

## 1. Model/system overview

| Field | Value |
|---|---|
| System name | ScholarMind |
| Version | 1.0.0 |
| Release | R7 (research release) |
| Type | Source-grounded scholarship intelligence system (retrieval + rules + LLM generation) |
| Components | Postgres 16 + pgvector + FTS · hybrid retrieval (RRF) · optional cross-encoder rerank · rule-based eligibility engine · snapshot diffing · Claude (family, version pinned per run) for interpretation/extraction |
| Primary users | African students applying to postgraduate scholarships (2027 intake) |
| Languages | English only (documented limitation) |

## 2. Intended use
- Discover scholarship opportunities from official sources.
- Assess eligibility requirement-by-requirement against a self-reported student profile.
- Report current deadlines, funding components, and required documents with source provenance.
- Plan applications (tasks, documents, personal deadlines) and notify users of changes to saved items.
- Answer natural-language questions about scholarships with cited evidence.

## 3. Out-of-scope use
- **Not** an admissions or success probability predictor. The ranking score is a prioritisation aid.
- **Not** a substitute for the official scholarship office. Where evidence is missing, the system says so.
- **Not** for automatic application submission or generating references, transcripts, or accomplishments.
- **Not** for legal/immigration or financial advice.
- **Not** for deciding that a student "will" win a scholarship.

## 4. Training data
- **No model training.** The system uses pre-trained, third-party models behind an API; no weights are
  fine-tuned. This is a deliberate research decision: it isolates the contribution to *architecture and
  evaluation*, not to training.
- **Retrieval corpus:** publicly available official scholarship pages, captured as snapshots for
  provenance and change detection (see Data Provenance).
- **Evaluation corpus:** a human-authored gold set (`data/fixtures/eval/`) plus a labelled
  scholarship–profile pair set and a change-replay set.

## 5. Evaluation results

> Fill from `research/experiments/*/results.json`. Report per class, with CIs. Do not publish an
> aggregate that hides a failing class.

### 5.1 Retrieval (Experiment A)
| System | Recall@5 | Recall@10 | MRR | nDCG@10 | p95 latency | cost/query |
|---|---|---|---|---|---|---|
| A0 Lexical | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| A1 Dense | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| A2 Hybrid (RRF) | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| A3 + Rerank | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| A4 + Engine + Freshness | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### 5.2 Answering (Experiment A)
| System | Correctness | Citation precision | Citation completeness | Correct-abstain | Wrong-answer rate | Conflict surfacing |
|---|---|---|---|---|---|---|
| A0 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| A4 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### 5.3 Eligibility (Experiment B)
| System | Rule P/R/F1 | Overall accuracy | **False-positive eligibility rate** | Correct-unknown rate | Needs-review recall |
|---|---|---|---|---|---|
| B0 LLM match score | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| B1 Rule engine | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| B2 Hybrid | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### 5.4 Freshness (Experiment C)
| Detector | Precision | Recall | Exact-value acc. | False-alarm rate | Median detection latency |
|---|---|---|---|---|---|
| C0 Naive diff | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| C1 Field-aware | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### 5.5 Ranking (Experiment D)
| System | nDCG@10 | Recall@10 | Rank stability (Kendall τ under ±20% weights) |
|---|---|---|---|
| D0 Weighted | _TBD_ | _TBD_ | _TBD_ |

## 6. Ablations
| Removed component | Metric affected | Δ | Note |
|---|---|---|---|
| Conflict detection | conflict surfacing / wrong-answer rate | _TBD_ | |
| Citation validation | hallucinated-fact rate | _TBD_ | |
| Eligibility engine | false-positive eligibility in answers | _TBD_ | |
| Freshness filter | expired-cycle answer rate | _TBD_ | |
| Reranker | Recall@10, nDCG@10, latency | _TBD_ | |

## 7. Evaluation methodology
See `docs/EVALUATION.md`. Summary:
- Gold set of 200–300 stratified items (fact, eligibility, conflict, prior-cycle, insufficient-evidence, adversarial), split dev/held-out, held-out used once per release.
- Metrics computed per class and per scholarship category with bootstrap CIs (n=1000).
- LLM judge used for answer correctness and citation support, calibrated against human labels (κ reported; if κ < 0.7 those metrics are human-scored only).
- System comparison uses paired differences with CIs.

## 8. Data provenance
| Source class | Example | Trust tier | Capture method | Notes |
|---|---|---|---|---|
| Government notices | Federal scholarship portals | official_primary | scheduled fetch + snapshot | Nigeria-first |
| Funder pages | Scholarship foundation sites | official_primary | scheduled fetch + snapshot | |
| University pages | Programme/funding pages | official_secondary | scheduled fetch + snapshot | |
| PDFs (official) | Call documents, guidelines | official_primary | sandboxed parse + snapshot | |
| Aggregators | Listing sites | aggregator | **not used for facts** | Discovery hints only, never a source of confirmed claims |

Every stored fact references a snapshot id, a character span, and a fetch timestamp.

## 9. Fairness & bias considerations
- Eligibility rules are transcribed from official sources; the risk is *mislabelling* a rule (e.g. a
  wording nuance), not discriminatory modelling. Mitigation: human review of every rule set, evidence
  spans, and a `needs_review` state for ambiguity.
- Coverage bias: the corpus is Nigeria-first, so opportunities relevant to other African nationalities
  are under-represented. Stated as a limitation; the schema and filters are Africa-wide from day one.
- Ranking fairness: the ranking model is transparent and does not use protected attributes; nationality
  appears only as an eligibility factor sourced from the rules. Sensitivity analysis is published.
- Language bias: English-only sources exclude some national schemes. Documented limitation.

## 10. Known failure modes
1. **Unrendered or gated pages** — facts may be missing; the system shows "not established" rather than guessing.
2. **Stale sources** — a deadline may have moved since the last check; freshness state is shown, but the staleness window is bounded by the refresh cadence.
3. **Rule mis-transcription** — a rule extracted incorrectly produces a wrong verdict; mitigated by evidence spans, review, and re-evaluation on rule-set version change.
4. **Ambiguous source wording** — surfaces as `needs_review` (a known failure of automated extraction, not a silent one).
5. **Silent source conflict** — two official pages disagree; the system refuses to assert a single value, which may frustrate users expecting one answer.
6. **Model drift** — a provider model update can change phrasing and support scores; pinned model versions per run, with the answer audit recording the model id.
7. **Profile incompleteness** — unknown verdicts dominate for users with sparse profiles; the UI pushes profile completion.
8. **Over-confidence in verification labels** — "confirmed" means "an official source stated it and we checked it", not "the information is correct in reality".

## 11. Ethical considerations
- Students make high-stakes decisions on this information. Design principle: when in doubt, abstain and
  point to the official scholarship office.
- No synthetic application content, no fabricated references, no document generation.
- Transparent ranking; no pay-to-rank placement; no sponsored listings in release 1–6.
- Minimise collection: the profile stores only what eligibility evaluation needs.

## 12. Model & system lifecycle
- Provider model pinned by id per run; prompt versioned and hashed into the audit record.
- Prompt/rule changes require re-running the held-out evaluation before release.
- Rule-set versions increment on any rule change; assessments are keyed by (engine version, ruleset version, profile hash).
- Deprecation: when a source is unreachable for > 30 days, it is flagged `stale` and excluded from "open" filters, and its records are labelled as potentially outdated in the UI.

## 13. Reporting limitations (must accompany any published figure)
- Corpus: 40–60 scholarships, Nigeria-first, English-only.
- Gold set authored by the project owner (second annotator where available, agreement reported).
- Change detection evaluated on replayed edits; real-world detection latency is bounded by the refresh cadence.
- Answer correctness relies on a calibrated LLM judge plus human sampling.
- Results are not evidence of performance on other regions, funders, or larger corpora.
