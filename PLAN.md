# ScholarMind — Platform Blueprint (v1)

> **AI-powered scholarship intelligence and application-strategy platform for African students.**
> Not a search wrapper around an LLM: a source-grounded decision-support system with temporal
> data, explicit eligibility reasoning, personalized ranking, and measurable reliability.

**Status:** blueprint written — Phase 01 (research & data audit) next
**Research core:** retrieval quality + eligibility accuracy + temporal change detection
**Product layer:** Discover · Verify · Compare · Plan · Ask · Track
**Intake targeted:** 2027 postgraduate cycles

---

## 1. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary differentiator (v1) | **Balanced** — grounded RAG + eligibility engine + freshness detection + discovery | Validation-first sequencing: the engine must be proven before UI investment |
| Flagship capability | **Eligibility Reasoning Engine** | Only capability a listings site cannot copy; highest false-positive cost |
| First corpus | **Nigeria-first, Africa-ready** — 40–60 manually reviewed opportunities | Nigerian government schemes (PTDF, NDDC, SETD, NNPC) + international postgraduate awards for Nigerians; schema and trust tiers already Africa-wide |
| Planner in first public release | **Yes, Release 1.5** (after engine validation, week 15) | Differentiator vs. listings sites; cheap once cycles/tasks exist |
| Research evaluation | **Core deliverable, not a side task** | The defensible artifact is the measured comparison, not the UI |
| Success bar | **Both** — defensible evaluation **and** production-grade product | |
| Timeline | **18 weeks**, 6 working releases | |
| Frontend | React 18 + TypeScript + Vite + Tailwind + TanStack Query + RHF/Zod | |
| Backend | Python 3.11 + FastAPI + Pydantic v2, modular monolith | |
| Data | PostgreSQL 16 + pgvector + `tsvector` FTS (BM25-style via `ts_rank_cd`) | Single DB first; separate search service only when measured |
| AI | Anthropic API (Claude) + embeddings, RRF hybrid retrieval, optional reranker | No framework lock-in; LangChain optional, not core |
| Workers | Celery + Redis (beat schedule) | Idempotent tasks, retries, admin visibility |
| Deploy | Docker → Railway/Fly (API + worker) + Vercel (web) + managed Postgres | |

Everything above is a **changeable default**. Each decision maps to a doc under `docs/`; changing one
requires updating that doc, not the code.

---

## 2. The six questions the product must answer

1. **What can I apply for?** — Relevant scholarships across funders, universities, governments.
2. **Am I eligible?** — Per-requirement verdicts: satisfied / not satisfied / unknown, with reasons.
3. **What is actually open?** — Deadline, opening date, cycle status, verified source and check time.
4. **How competitive is my profile?** — Strengths, gaps, improvable levers. **Never** a probability of winning.
5. **What should I do next?** — Prioritized, deadline-aware, document-aware application plan.
6. **Can I trust this?** — Every material claim traced to source, snapshot version, and check timestamp.

If the system cannot answer one of these with evidence, it must say so rather than guess.

---

## 3. Capability spine

| # | Capability | Kind | Release |
|---|---|---|---|
| 1 | **Eligibility Reasoning Engine** | Research core | R1 (engine) / R3 (UI) |
| 2 | **Scholarship Change Intelligence** | Research core | R2 |
| 3 | **Evidence Ledger & Contradiction Detector** | Research core | R1 |
| 4 | **Hybrid Retrieval & Grounded Answers** | Research core | R1 |
| 5 | **Application Strategy Planner** | Product | R1.5 |
| 6 | **Opportunity Pathway Graph** | Product | R2 |
| 7 | **Scholarship Intelligence Research Lab** | Research | R1 (dataset) → R6 (report) |
| — | Discovery, Compare, Dashboard, Assistant UI | Product | R3 |
| — | Readiness Studio (document/achievement mapping) | Product | R4 |

**Ordering principle:** corpus → evidence → retrieval → eligibility → freshness → UI → planner → hardening.

---

## 4. The three-layer intelligence framework

**Layer 1 — Structured facts.** Scholarships, cycles, eligibility rules, funding components, dates.
Stored as typed columns, never as prose in a vector store. This layer is the authority.

**Layer 2 — Evidence & temporal state.** Every fact carries provenance: official source, snapshot id,
hash, fetch time, extraction confidence, and change history. Facts carry a status:
`confirmed` · `stale` · `ambiguous` · `unresolved` · `conflicting`.

**Layer 3 — Reasoning & recommendation.** Eligibility verdicts, ranking scores, plan priorities, and
natural-language answers — all computed *from* Layers 1–2, never inventing facts.

```
Official sources → Ingestion → Snapshots → Extraction → Normalization
        │                                                      │
        │                                     Layer 1 + 2 (Postgres)
        ▼                                                      ▼
   Change detection  ←───────────────────────────  Evidence ledger
        │                                                      │
        ▼                                                      ▼
 Layer 3: eligibility · ranking · planner · grounded answers (LLM interprets, never authors facts)
```

**The one rule that defines this product:** the LLM is *not* the authority on scholarship facts.
Rules and structured records decide eligibility, deadlines, funding and status. The LLM interprets
source text, explains results, and answers nuanced questions — with abstention built in.

---

## 5. Research questions

Central question:

> Can a source-grounded scholarship intelligence system combining hybrid retrieval, structured
> eligibility reasoning and temporal change detection improve the accuracy, freshness and practical
> usefulness of scholarship guidance compared with a conventional RAG baseline?

Sub-questions (each maps to an experiment in §9):

- **RQ1 (retrieval)** Does hybrid + RRF + reranking improve Recall@k / nDCG over lexical and dense alone?
- **RQ2 (generation)** Does evidence-constrained generation with citation validation reduce unsupported claims and improve correct abstention?
- **RQ3 (eligibility)** Does explicit rule evaluation reduce false-positive eligibility versus LLM-scored matching, and at what cost in unknowns?
- **RQ4 (freshness)** Can change detection reliably identify deadline/funding/eligibility edits, and at what false-alarm rate?
- **RQ5 (ranking)** Is a transparent weighted ranking defensible, and how sensitive is it to weight choice?
- **RQ6 (trust)** Does conflict surfacing prevent misleading answers on contradictory sources?

**Claim discipline:** no quantitative claim ships until measured on the held-out set. All numbers in
the portfolio write-up come from `research/experiments/*/results.json`, generated by the harness.

---

## 6. Data model (authoritative summary)

Full definitions in `docs/DATA_DICTIONARY.md`.

| Entity | Purpose | Key relations |
|---|---|---|
| `scholarships` | Stable identity, provider, destinations, fields, canonical page | → cycles, sources, rules |
| `scholarship_cycles` | Intake year, open date, deadline, status, cycle-scoped terms | → scholarships, cycle rules |
| `eligibility_rules` | Typed conditions: nationality, degree level, age, GPA, field, language, experience | → cycles |
| `funding_components` | Tuition / stipend / travel / accommodation / insurance, coverage status | → cycles |
| `source_documents` | Official URL, source type, trust tier, last checked, fetch status | → snapshots |
| `source_snapshots` | Immutable captures: hash, fetched_at, extracted text, HTTP metadata | → evidence, changes |
| `evidence_claims` | Atomic claim + span + snapshot + claim type + validation status | → answers, assessments |
| `change_events` | old value, new value, detected_at, severity, review status, affected cycle | → snapshots |
| `student_profiles` | User facts, qualifications, preferences | → assessments, applications |
| `eligibility_assessments` | Per-rule verdict, evidence ids, unknowns, engine version | → profiles, cycles |
| `saved_scholarships` | Shortlist + notes | → profiles |
| `applications` | Status, target cycle, plan metadata | → profiles, cycles |
| `application_tasks` | Action, due date, done, dependency, doc type | → applications |
| `answer_audits` | Query, retrieved evidence ids, citations, model/prompt version, validation outcome | → evidence |

**Design invariants:**
- `scholarships` ≠ `scholarship_cycles`: an award spans years; its deadline, funding and rules change per cycle.
- Funding is stored **per component** with status `included | excluded | conditional | unknown` — never one "fully funded" boolean.
- Eligibility is tri-state minimum: `satisfied | not_satisfied | unknown`, plus `needs_review` for conflicts.
- Every fact row carries `source_snapshot_id` + `checked_at`; facts without provenance are not stored.

---

## 7. System architecture

Modular monolith + workers. No microservices without a measured need.

```
apps/web (React/TS)          → Vercel / static CDN
        │ HTTPS / JSON
services/api (FastAPI)       → Docker → Railway / Fly
        │
        ├── PostgreSQL 16 (pgvector + FTS)   → managed (Neon/Supabase/RDS)
        ├── Redis                            → managed
        └── services/worker (Celery)         → Docker, same image family
              ├── ingest.scheduled_sources
              ├── ingest.fetch_snapshot
              ├── extraction.extract_facts
              ├── normalization.normalize_cycle
              ├── freshness.diff_snapshots
              ├── freshness.flag_changes
              ├── alerts.dispatch_notifications
              ├── reports.generate_export
              └── evaluation.run_benchmark
```

**Domain logic is framework-free.** `services/api/app/services/*` calls into the importable
`scholarmind/*` core package (ingestion, extraction, normalization, eligibility, retrieval,
generation, freshness, evaluation, reporting). The API layer owns HTTP, auth, pagination, rate
limits. Retrieval, evaluation, citation validation and eligibility logic are independently testable
without FastAPI, Celery or an LLM provider.

**Module map (core package):**

| Module | Responsibility | Key invariant |
|---|---|---|
| `ingestion/` | Fetch official pages safely, snapshot them | Allowlisted domains, SSRF guard, idempotent by URL+content hash |
| `extraction/` | Extract typed facts + evidence spans | Every fact carries a span offset into its snapshot |
| `normalization/` | Normalize cycles, countries, degrees, funding, dates | Idempotent; stores original + normalized value |
| `eligibility/` | Evaluate rules against profile facts | Unknown never coerced to satisfied; every verdict has a reason |
| `retrieval/` | Lexical + dense + RRF + rerank | Pure functions, no network, no DB in unit tests |
| `generation/` | Evidence-constrained answers + citation validation | Model returns claim→evidence-id map; ids must exist in context |
| `freshness/` | Diff snapshots, classify changes, detect conflicts | Flags for review; never auto-mutates a confirmed fact silently |
| `evaluation/` | Harness, metrics, baselines, ablations | Deterministic given pinned seeds + dataset version |
| `reporting/` | Exports (checklists, comparison, evidence report) | Reproducible output, same input → same file |

---

## 8. Retrieval & answering design

**Hybrid retrieval.** `ts_rank_cd` lexical (BM25-like) + pgvector cosine → Reciprocal Rank Fusion
(k=60) → optional cross-encoder rerank. Unit of retrieval = **evidence chunk**, not page.

**Answer pipeline:**
1. Retrieve candidate chunks (hybrid, k≈40).
2. Assemble context with stable evidence IDs and snapshot metadata.
3. Generate with a structured output contract:
   ```json
   {"claims":[{"text":"...","evidence_ids":["ev_..."],"confidence":"confirmed|uncertain"}],
    "abstained":false,"abstention_reason":null,"follow_up_questions":[]}
   ```
4. **Validate:** (a) every cited id existed in the context, (b) cited chunk lexically/structurally
   supports the claim, (c) dates/amounts cross-checked against Layer 1 records when present,
   (d) if validation fails → downgrade to "needs verification" or abstain.
5. Log the audit record (`answer_audits`) with model version, prompt version, retrieval config,
   snapshot ids and validation outcome.

**Prompt-injection defence:** retrieved page text is data, never instruction. Allowlisted source
domains, sanitized extraction, instruction-isolation prompt block, output-schema validation, and a
corpus of injection-attack evaluation items (a labelled set, not a hope).

---

## 9. Research plan

Full protocol in `docs/EVALUATION.md`.

| Exp | Question | Systems compared | Headline metrics |
|---|---|---|---|
| **A** | Retrieval & answer quality | A0 lexical → A1 dense → A2 hybrid RRF → A3 +rerank → A4 +engine+freshness | Recall@5/10, MRR, nDCG, answer correctness, citation precision/completeness, correct-abstain, contradiction handling, latency & cost |
| **B** | Eligibility reasoning | LLM-scored match vs. explicit rule engine vs. hybrid (LLM-extracted + validated rules) | Rule-level P/R/F1, overall accuracy, **false-positive rate**, correct-unknown rate |
| **C** | Temporal freshness | Change detector vs. naive "page text differs" | Precision/recall by change type, exact-value accuracy, detection latency, false-alarm rate, human-verified share |
| **D** | Personalized ranking | Transparent weighted baseline vs. perturbed weights | nDCG@k, Recall@k, weight-sensitivity / rank-stability analysis |

**Dataset:** `data/fixtures/eval/*.jsonl` — 200–300 gold items at target, 60–100 to develop the
pipeline. Item classes: exact-fact, multi-condition eligibility, conflicting-source, prior-cycle,
and **insufficient-evidence** (correct answer = abstain). Each item carries required evidence ids.

**Split discipline:** dev items used during development; held-out items used once per release.
Dataset version + split ids recorded in every results file. No tuning on held-out.

---

## 10. Release plan (18 weeks)

| Weeks | Release | Deliverable | Exit condition |
|---|---|---|---|
| 01–02 | **R0 — Foundation & research design** | Source inventory & permissions audit, SRS, data dictionary, schema, eval protocol, RQs | Approved scope + testable eval plan + 30-source manifest |
| 03–04 | **R1 — Corpus & data engineering** | 40–60 scholarships with snapshots, extracted facts, normalized cycles, admin review queue, validation report | Reproducible corpus w/ provenance; every record has official source + check time |
| 05–07 | **R2 — Retrieval & grounded answers** | Lexical + dense baselines, RRF, rerank, citation validation, abstention, gold set v1 | Reproducible A0–A3 comparison + failure analysis |
| 08–10 | **R3 — Eligibility & temporal intelligence** | Rule engine, snapshot diffing, change classification, conflict detection, labelled eligibility set | Measured eligibility + change-detection performance; false-positive rate reported |
| 11–13 | **R4 — Web application** | Auth, dashboard, discovery, details, compare, eligibility views, assistant | A student can discover, inspect evidence, and see rule-level verdicts |
| 14–15 | **R5 — Planner & freshness alerts** | Shortlist, doc checklists, task dependencies, source history, opt-in reminders, export | End-to-end planning workflow; scheduled jobs + retries verified |
| 16–17 | **R6 — Hardening & deployment** | Integration/E2E tests, rate limits, authz, monitoring, backups, Docker, smoke tests | Stable public app + operational docs + restore test |
| 18 | **R7 — Research release** | Ablations, error analysis, system & data card, architecture diagram, demo video, case study | Published results match measured outputs only |

Release discipline: a release is not "done" if its exit condition is unmet, regardless of schedule.

---

## 11. Trust contract (interface + backend rules)

**User-facing claim states:**

| State | Meaning | UI treatment |
|---|---|---|
| `confirmed` | Official source explicitly states it; source checked | Green chip, source link, snapshot time |
| `not_established` | Reviewed material does not establish it | Amber chip + "what we still need" / contact prompt |
| `needs_verification` | Two official sources conflict | Red chip, both sources shown, no single deadline asserted |
| `stale` | Source unreachable since last check | Grey chip + "last verified <date>" |
| `expired` | Cycle deadline passed | Muted, excluded from "open" filters by default |

**Backend invariants:**
1. Every retrieved excerpt gets a stable evidence id.
2. Generation returns claim→evidence-id mapping; ids must exist in the retrieved context.
3. Support check goes beyond "the URL appears" — the referenced span must plausibly entail the claim.
4. Dates/amounts in prose are reconciled against Layer 1 records.
5. Insufficient evidence → abstain or request the missing profile field.
6. Every answer logged with model version, prompt version, retrieval config, snapshot ids, validation result.
7. LLM judge assists triage only; a human-labelled set validates the judge itself.

---

## 12. Frontend surface

| Page | Purpose | Key elements |
|---|---|---|
| Dashboard | Orientation | Priority opportunities, deadlines, missing profile fields, upcoming tasks, recent verified changes |
| Discover | Search & filter | Filters: nationality, level, field, destination, funding component, cycle, verification status; official link prominent on every card |
| Scholarship Detail | Evidence-first view | Cycles, rule-by-rule eligibility, funding breakdown, source status, change history, "ask about this" |
| Compare | Side-by-side | Rule-level verdicts, funding components, deadline status, unknown conditions, freshness per source |
| Eligibility | Profile + analysis | Profile completion meter, per-rule verdicts with reasons, missing-info prompts, re-evaluate |
| Planner | Execution | Saved items, doc checklist, dependencies, personal deadlines, export, opt-in reminders |
| Assistant | Grounded Q&A | Answer, claim list, cited excerpts with snapshot time, freshness warnings, conflict banners, "evidence insufficient" state |
| Change History | Transparency | Timeline of detected changes per source, old → new, detection time, review status |
| Settings | Control | Profile, notifications, data export, delete account, source trust preferences |

**UX rules:** loading / empty / error / stale states on every data surface; claim states always
visible; keyboard navigable; mobile-first responsive; no metric presented as a probability of success.

---

## 13. API surface (v1)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/scholarships` | Search & filter (pagination, typed filters) |
| GET | `/api/v1/scholarships/{id}` | Details, cycles, eligibility summary, source status |
| GET | `/api/v1/scholarships/{id}/history` | Cycle + source change history |
| GET | `/api/v1/scholarships/{id}/evidence` | Evidence claims for the record |
| POST | `/api/v1/eligibility/evaluate` | Profile vs. rules → per-rule verdicts |
| GET | `/api/v1/eligibility/explain/{assessment_id}` | Human-readable reasoning trace |
| POST | `/api/v1/assistant/ask` | Evidence-grounded answer |
| POST | `/api/v1/assistant/verify` | Re-validate a stored answer audit |
| POST | `/api/v1/compare` | Compare shortlisted items |
| GET | `/api/v1/recommendations` | Explainable personalized ranking |
| POST | `/api/v1/saved` / DELETE | Shortlist management |
| POST | `/api/v1/applications` / GET | Application plans |
| GET | `/api/v1/tasks` / PATCH `/api/v1/tasks/{id}` | Task tracking |
| POST | `/api/v1/alerts` | Opt-in deadline / change alerts |
| GET | `/api/v1/sources/{id}/history` | Snapshot history |
| GET | `/api/v1/admin/ingestion/jobs` | Admin queue visibility (admin role) |
| POST | `/api/v1/admin/reviews/{change_id}` | Approve/reject a flagged change (admin role) |
| GET | `/api/v1/health` | Liveness + dependency health |

Conventions: cursor pagination, typed Pydantic response models, RFC-7807-style errors, JWT auth with
refresh, role checks (student / admin / researcher), rate limits on write and assistant endpoints,
admin endpoints on a separate router with stricter auth.

---

## 14. Data & ingestion pipeline

1. **Manifest** (`data/manifests/*.yaml`): canonical URLs, source type, trust tier, refresh cadence, country scope, cycle target, notes.
2. **Fetch**: allowlisted host, robots-aware courtesy delay, conditional requests (ETag/Last-Modified), size + content-type caps, SSRF guard (no private ranges, no redirects to private IPs), timeout + retry with backoff.
3. **Snapshot**: raw HTML/PDF text + headers + content hash + fetched_at → `source_snapshots` (immutable).
4. **Extract**: LLM-assisted extraction with a strict typed schema, each field carrying the character span it came from; low-confidence fields flagged for human review, never silently accepted.
5. **Normalize**: cycles, dates (explicit timezone + "as stated" fallback), countries (ISO-3166 alpha-3), degree levels, funding components, field taxonomies.
6. **Diff** against the previous snapshot → candidate change events → classifier → severity → admin review queue.
7. **Publish**: only reviewed or high-confidence facts change `confirmed` status; everything else lands as `ambiguous`/`unresolved`.

**Refresh policy:** weekly for most sources; daily for sources with known deadline churn; on-demand
for user-visible "refresh" requests (rate-limited). Every record shows `last_checked_at`.

---

## 15. Security & privacy

- Secrets only in env/secret manager; never in client bundles or repo. `.env.example` is committed, `.env` is not.
- PII (student profiles, uploaded documents) stored with encryption at rest; minimal retention; user export + delete endpoints.
- Assistant sees only the retrieved evidence of the question — no cross-user data leakage; authorization checks on every user-scoped query.
- Fetch hardening: SSRF protection, host allowlist, HTML sanitization, prompt-injection isolation, PDF parse sandboxing.
- Rate limits on assistant + ingestion-adjacent endpoints; API key rotation documented; audit log for admin actions.
- LLM provider privacy note: profile facts are minimized before being sent; document contents are not sent unless the user opts in.

Details: `docs/SECURITY.md`.

---

## 16. Evaluation & research-lab instrumentation

Every answer and every eligibility assessment is an experiment unit. Metrics computed offline from
stored artifacts, not recomputed from live systems.

- `research/evaluation/` — harness, metric implementations, dataset schema, split tooling, report builders.
- `research/experiments/` — one directory per experiment run: config, dataset version, results.json, analysis.md.
- `research/paper/` — figures, tables, method description, limitations.
- Tracking per question type and per scholarship category (not one aggregate number).

Required reporting: baselines, ablations, failure cases with examples, dataset provenance, splits,
software versions, latency and cost.

---

## 17. Release-readiness tracker (0/22)

**Data integrity**
1. Every scholarship has a canonical official source + recorded check time.
2. Cycles and deadlines stored separately from awards.
3. Missing / conflicting / stale facts never render as confirmed.
4. Snapshots and changes are auditable end to end.
5. Every extracted fact traces to a span in a snapshot.

**AI reliability**
6. Every material claim traces to supporting evidence.
7. Invalid or unsupported claims trigger abstention or clarification.
8. Eligibility distinguishes satisfied / not satisfied / unknown.
9. Evaluation covers expired cycles, conflicting pages, injection attempts.
10. Citation-validator quality itself is validated against human labels.

**Web application**
11. Loading / empty / error / stale states implemented.
12. API schemas, pagination, authorization tested.
13. Profiles and documents protected; no cross-user access.
14. Mobile + desktop + keyboard navigation verified.

**Operations**
15. Secrets never committed or exposed to the browser.
16. Workers have retries, monitoring and failure alerts.
17. Migrations and backup restoration tested.
18. Health checks, rate limiting, logs and rollback procedure in place.

**Research release**
19. Retrieval and generation evaluated separately.
20. Baselines, ablations and failure cases reported.
21. Dataset provenance, splits, software versions documented.
22. Limitations and unsupported claims stated explicitly.

---

## 18. Top risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Official pages are JS-rendered / PDFs / gated | Ingestion coverage collapses | Per-source adapters, headless fallback where permitted, manual corpus entry for high-value sources (always with provenance) |
| Deadline changes silently | Students miss applications | Snapshot diffing + conflict detection + opt-in alerts; never assert a single date from conflicting sources |
| False-positive eligibility | Student wastes a cycle | Tri-state verdicts, unknown bucket, false-positive rate as a headline metric, abstain when facts are missing |
| LLM invents requirements | Trust collapse | Rules are validated + typed; LLM only proposes candidate rules; every fact needs a span + review |
| Evaluation set too small / biased | Research claims indefensible | Stratified item classes, held-out split, publish dataset + annotator protocol, report CIs |
| Scraping/ToS & politeness | Legal/ethical risk | Allowlisted manifest, courtesy rates, robots awareness, prefer official APIs/feeds, cache aggressively |
| Scope creep into microservices | Schedule slip | Modular monolith + workers; new service requires a measured trigger |
| Silent failure when a source 404s | Stale data shown as fresh | `stale` claim state + "last verified" + fetch-status monitoring |

---

## 19. Definition of done (final deliverables)

1. **Live web application** — React + FastAPI: discovery, rule-level eligibility, grounded Q&A with citations, source history, application planner.
2. **Versioned corpus** — 40–60 scholarships, snapshots, cycles, rules, data-quality report.
3. **Research evaluation** — baselines vs. hybrid, citation & answer correctness, eligibility accuracy (incl. false-positive rate), abstention, change detection, ranking sensitivity, error analysis.
4. **System & data card** — intended use, data provenance, limitations, freshness policy, privacy controls, known failure modes.
5. **Reproducible repository** — tests, migrations, Docker, CI, deployment docs, architecture diagram, demo.

---

## 20. Immediate next actions (week 1)

1. Create the source manifest for the Nigeria-first corpus (30 candidate official URLs) → `data/manifests/`.
2. Write `docs/SRS.md` (scope, requirements, acceptance criteria) and `docs/DATA_DICTIONARY.md` (final table set).
3. Stand up Postgres + pgvector locally via `infra/docker-compose.yml`; create Alembic migrations for the v1 schema.
4. Build the ingestion skeleton: fetch → snapshot → hash, with the SSRF guard and allowlist implemented first.
5. Author 40 gold evaluation items across the five item classes (facts, eligibility, conflicts, prior cycles, abstain).
6. Set up `research/evaluation/` harness with lexical-only baseline and a deterministic metric runner.

---

*Blueprint v1 — Companion docs: `SRS.md`, `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `EVALUATION.md`, `SECURITY.md`, `MODEL_CARD.md`, `DEPLOYMENT.md` (all under `docs/`).*
