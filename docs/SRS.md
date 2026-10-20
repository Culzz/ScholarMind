# ScholarMind — Software Requirements Specification (SRS)

**Version:** 1.0 · **Owner:** Hamayl Zahid · **Status:** Draft for review
**Scope:** Release 1 → 6 (see `PLAN.md` §10). Post-release-6 features are out of scope and listed in §12.

---

## 1. Purpose

ScholarMind is a scholarship intelligence and application-strategy platform for African students
targeting the 2027 postgraduate intake. It discovers opportunities, evaluates eligibility
requirement-by-requirement, tracks source freshness and changes, and plans applications — with
every material claim traceable to an official source, a snapshot version, and a check timestamp.

## 2. Definitions

| Term | Definition |
|---|---|
| Scholarship | A stable, named funding opportunity with a provider (funder, university, government). |
| Cycle | A specific application round of a scholarship (e.g. "Chevening 2027"). Carries its own dates, rules, funding. |
| Source document | An official page/document that the system treats as authoritative for a fact. |
| Snapshot | An immutable capture of a source document at a point in time. |
| Evidence claim | An atomic factual statement bound to a span inside a snapshot. |
| Eligibility rule | A typed, machine-checkable condition attached to a cycle. |
| Assessment | The per-rule evaluation of one profile against one cycle. |
| Claim state | `confirmed`, `not_established`, `needs_verification`, `stale`, `expired`. |

## 3. Users & roles

| Role | Needs | Auth |
|---|---|---|
| Student | Discover, verify, compare, plan, ask | Email + password (JWT access/refresh), optional Google OAuth |
| Researcher | Access to the evaluation harness, datasets, experiment results | Staff account, read-only on prod data |
| Admin | Review flagged changes, manage source manifest, monitor ingestion | Staff account + admin role claim |

Students may be anonymous-browsing (discovery without saving), but profile-dependent features
(eligibility, planner, alerts) require an account.

## 4. Functional requirements

### FR-1 Discovery
- FR-1.1 Search by keyword across scholarships, cycles, and evidence chunks.
- FR-1.2 Filter by: nationality eligibility, degree level, field of study, destination country/region, funding component status, cycle year, verification status, deadline window.
- FR-1.3 Sort by: deadline (default for open cycles), relevance, funding coverage confidence, verification status.
- FR-1.4 Every result card shows the official link, deadline, cycle, and source check time.
- FR-1.5 Results are paginated (cursor-based) and filter combinations are valid against the API schema.

### FR-2 Scholarship detail
- FR-2.1 Show all known cycles with open date, deadline, status, and rule count.
- FR-2.2 Show funding as a component breakdown (tuition, stipend, travel, accommodation, insurance), each `included | excluded | conditional | unknown`, with evidence links.
- FR-2.3 Show source status: canonical source, trust tier, last checked, next scheduled check, last fetch error (if any).
- FR-2.4 Show change history for the scholarship and its source.
- FR-2.5 Show the eligibility summary for the signed-in student's profile, or a prompt to complete the profile.

### FR-3 Eligibility Reasoning Engine
- FR-3.1 Evaluate each rule of a cycle independently against profile facts.
- FR-3.2 Verdict per rule ∈ {`satisfied`, `not_satisfied`, `unknown`, `needs_review`}; `needs_review` is used when evidence is conflicting or the rule text is ambiguous.
- FR-3.3 Every verdict carries: the rule text, the profile fact used (or the missing fact), a human-readable explanation, and supporting evidence ids.
- FR-3.4 A missing profile fact yields `unknown` — never `satisfied`.
- FR-3.5 Assessments are versioned by engine version + rule-set version and are re-runnable; previous assessments are retained.
- FR-3.6 Assessment returns, per cycle: verdict counts, a top-level summary label, and the list of facts that would resolve open unknowns.
- FR-3.7 Engine evaluation is deterministic and unit-testable without network or LLM access.

### FR-4 Scholarship Change Intelligence
- FR-4.1 Capture a snapshot on every scheduled or manual check; snapshots are immutable and content-addressed.
- FR-4.2 Diff the current snapshot against the previous one and produce candidate change events with field, old value, new value, and detection timestamp.
- FR-4.3 Classify candidate changes by type: deadline, opening date, funding, eligibility, required documents, contact/portal, cosmetic.
- FR-4.4 Candidate changes are flagged for review; a change only alters a confirmed fact after validation (automated confidence threshold or admin approval).
- FR-4.5 Conflicting values for the same field across two official sources are recorded as a conflict, not silently resolved.
- FR-4.6 A failed fetch marks the source `stale`; it never marks the opportunity closed.

### FR-5 Evidence Ledger & Contradiction Detector
- FR-5.1 Every extracted fact references a snapshot id and a text span.
- FR-5.2 Facts carry validation status: `confirmed`, `ambiguous`, `unresolved`, `conflicting`, `stale`.
- FR-5.3 The UI surfaces claim state for every material fact; `confirmed` styling requires the source to be checked within the freshness policy.
- FR-5.4 When two official sources disagree on a material field, both values are shown with source, snapshot time, and trust tier; the system asserts neither as final.

### FR-6 Grounded Assistant
- FR-6.1 Answers are generated only from retrieved evidence chunks.
- FR-6.2 Answers return a claim list; each claim names the evidence ids supporting it.
- FR-6.3 Validation checks: cited ids existed in context; referenced span plausibly supports the claim; dates/amounts reconcile with structured records where available.
- FR-6.4 When evidence is insufficient, the assistant abstains, states what is missing, and suggests the next action (e.g. complete a profile field, contact the scholarship office).
- FR-6.5 Answers include freshness warnings when a cited source is stale or the relevant cycle is expired.
- FR-6.6 Every answer is persisted as an `answer_audit` with model, prompt, retrieval config, snapshot ids, and validation outcome.
- FR-6.7 Retrieved page content is treated as untrusted data; injection attempts in source text must not change assistant behaviour (covered by evaluation).

### FR-7 Comparison
- FR-7.1 Compare 2–5 scholarships side by side.
- FR-7.2 Comparison includes: rule-level verdicts, funding component breakdown, deadline & status, unknown conditions, source freshness, and unresolved conflicts.
- FR-7.3 The comparison report is exportable (PDF/Markdown).

### FR-8 Application Strategy Planner
- FR-8.1 Save a scholarship to a shortlist with notes.
- FR-8.2 Create an application plan targeting a specific cycle.
- FR-8.3 Auto-generate a task checklist from the cycle's required documents and personal deadlines.
- FR-8.4 Tasks support: title, due date, type (document / form / request / submission), completion, dependency on another task, and notes.
- FR-8.5 Document-request tasks are back-scheduled from the application deadline by a configurable preparation buffer.
- FR-8.6 Plan export to Markdown/CSV/PDF checklist.
- FR-8.7 Opt-in reminders for personal deadlines, cycle opening, cycle closing, and detected changes to saved scholarships.

### FR-9 Recommendations & ranking
- FR-9.1 Recommendations return a transparent weighted score with the contributing factors and their values shown.
- FR-9.2 The score is labelled a prioritisation aid, never a probability of admission or success.
- FR-9.3 Factors: confirmed eligibility ratio, degree/field alignment, funding fit against preferences, destination & study-mode preferences, deadline feasibility, estimated preparation effort.
- FR-9.4 Ranking is reproducible: same profile + same data snapshot → same ordering (documented weights, recorded version).

### FR-10 Admin & operations
- FR-10.1 Admin queue lists ingestion jobs with status, attempts, and error detail.
- FR-10.2 Admin can review flagged changes (approve/reject with reason) and edit structured fields with an audit trail.
- FR-10.3 Admin can add/pause/disable a source in the manifest and set its refresh cadence.
- FR-10.4 Admin can trigger a manual re-check of a source.
- FR-10.5 Admin sees corpus health: sources failing, facts unconfirmed, conflicts open, coverage by country/funder.

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Assistant answers: p95 end-to-end ≤ 8 s (excluding model queue); retrieval stage ≤ 1.5 s p95. |
| NFR-2 | Discovery API p95 ≤ 400 ms for a filtered page of 25. |
| NFR-3 | Every user-scoped endpoint enforces authorization; cross-user access is impossible (integration-tested). |
| NFR-4 | 100% of scheduled ingestion jobs are idempotent; retries are bounded and visible. |
| NFR-5 | Secrets never appear in client bundles, logs, or the repository. |
| NFR-6 | All DB changes via Alembic migrations; migration + rollback tested. |
| NFR-7 | Core domain packages (`scholarmind/*`) import with no HTTP framework, DB session, or LLM provider required. |
| NFR-8 | Health endpoint reports Postgres, Redis, and worker heartbeat status. |
| NFR-9 | PII encrypted at rest; export and delete flows implemented and tested. |
| NFR-10 | UI meets WCAG 2.1 AA basics: keyboard navigation, focus visibility, contrast, semantic labels. |
| NFR-11 | Backups: daily automated, restore rehearsed at least once per release. |
| NFR-12 | Every scheduled source has a freshness policy; records older than 2× cadence display as `stale`. |

## 6. Data requirements
- Schema per `docs/DATA_DICTIONARY.md`; migrations from Alembic.
- Corpus target: 40–60 manually reviewed opportunities for release 1 (Nigeria-first, Africa-ready).
- Gold evaluation set: 60–100 items during development, 200–300 before the research release.
- Every corpus row carries canonical official URL, snapshot, and check time before publication.

## 7. API requirements
- REST under `/api/v1`, JSON, OpenAPI generated from Pydantic models.
- Cursor pagination with stable sort + tiebreaker.
- Typed errors with a machine-readable code, human-readable message, and request id.
- Rate limits on assistant, alert, and refresh endpoints; larger limits for authenticated reads.

## 8. Acceptance criteria (release 1 / engine validation)
1. A student can complete a profile and receive per-rule verdicts for ≥ 10 scholarships, each with a reason and evidence.
2. Every verdict is `unknown` (not `satisfied`) when the required profile fact is missing — verified by an automated test over all rule types.
3. `POST /assistant/ask` returns claims with resolvable evidence ids for every factual claim; a deliberately unsupported question returns an abstention.
4. The evaluation harness reproduces baseline numbers for A0 and A2 on the dev split from a clean checkout.
5. Changing a stored snapshot triggers a candidate change event with old/new value and no automatic fact mutation.

## 9. Out of scope for releases 1–6
- Automatic application submission on external portals.
- Reference-letter or document generation (no fabricated accomplishments or references).
- Admissions probability or success-rate prediction.
- Native mobile applications.
- User-uploaded documents for automatic eligibility extraction (planned as an opt-in research extension in release 4+).

## 10. Dependencies & constraints
- Official source availability and page structure (external, partly out of our control).
- LLM provider rate limits and cost; caching and batching required.
- pgvector index build time on a cold DB; plan a concurrent index migration for large corpora.

## 11. Open questions
1. Do we serve Nigeria-only eligibility in release 1, or accept other African nationalities in the profile schema from day one? *(Decision: schema Africa-wide, corpus Nigeria-first.)*
2. Is a reranker worth the added latency/cost at corpus size 60? *(Decide at week 7 via A2 vs A3.)*
3. Email vs. in-app reminder delivery for release 5? *(Default: in-app + email via provider.)*
4. Do we need multi-language source pages (FR/EN)? *(Default: EN only; note as a documented limitation.)*

## 12. Post-release roadmap
- Release 7+: Opportunity Pathway Graph, Readiness Studio, collaborative shortlists, institution dashboards, API for third-party advisers, personalization from consented feedback (not synthetic clicks).
