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
- FR-10.6 Admin sees scam signals raised against sources, with the trust-tier demotion they caused.
- FR-10.7 Admin can review community corrections and promote a verified correction into a change event.

### FR-11 Claim-level verification
- FR-11.1 Every generated claim is checked against the excerpt it cites by an entailment verifier.
- FR-11.2 A claim that fails verification is removed from the answer or marked `⚠️ unverified`; it is never presented as supported.
- FR-11.3 The verifier used is recorded on the answer audit so results are reproducible.
- FR-11.4 A model-based judge may only act as the primary verifier after it has been validated against human labels (Cohen's κ ≥ 0.7); until then it runs alongside the deterministic verifier.

### FR-12 Unlock Paths (counterfactual eligibility)
- FR-12.1 For a profile and a shortlist, the system computes the profile changes that would make additional cycles eligible.
- FR-12.2 Unlock paths are produced by re-running the deterministic rule engine against mutated profiles — never by model speculation.
- FR-12.3 A path is offered only when the whole cycle becomes eligible; a cycle that still fails another mandatory rule is not counted as unlocked, and the remaining blockers are listed.
- FR-12.4 Every path cites the rules it changes, the evidence behind them, and the effort the change implies.
- FR-12.5 The response is explicitly a prioritisation aid, never a probability of success.

### FR-13 Smart Question Engine
- FR-13.1 The system asks one profile question at a time, chosen by information gain: the number of open unknowns it resolves across the shortlist, weighted by rule importance.
- FR-13.2 A field the student has already supplied is never asked again.
- FR-13.3 A requirement that is ambiguous rather than missing is not turned into a question the student cannot answer.
- FR-13.4 The endpoint returns the ranked questions, the recommended next question, and the current resolution rate.

### FR-14 Conflict resolution
- FR-14.1 When official sources disagree, both values are stored and surfaced; neither is asserted as final.
- FR-14.2 A resolution is proposed using the trust hierarchy `official_primary > official_secondary > partner > aggregator`.
- FR-14.3 Material fields (deadline, opening date, funding, eligibility, required documents) always require human review before the conflict can be closed.
- FR-14.4 Sources with equal trust tier are never resolved automatically.

### FR-15 Cycle prediction
- FR-15.1 The next opening window may be estimated from previous cycles, labelled as an estimate.
- FR-15.2 Predictions are stored only in `cycle_predictions`, are never used to answer "is this open?", and never satisfy an eligibility rule.
- FR-15.3 A prediction requires at least two past cycles and records the snapshots it was derived from.

### FR-16 African-applicant capabilities
- FR-16.1 Grade mapper: converts First Class / Second Class Upper / Second Class Lower / CGPA 5.0 / CGPA 4.0 / GPA 4.0 / credit / percentage between scales using documented anchors and band thresholds, always to the conservative lower bound.
- FR-16.2 Every conversion is marked exact or approximate, and an approximate cross-scale comparison yields `needs_review` rather than a confident verdict.
- FR-16.3 Waiver rules (English-medium degree, prior English-medium study, accepted exemptions) are stored per cycle with evidence and are never assumed globally.
- FR-16.4 The backward planner accounts for document lead times including transcripts, referees, NYSC certificates, credential evaluation, notarisation and apostille.
- FR-16.5 Scam signals (look-alike domains, application fees on unofficial sites, missing contact details, non-official portals) demote a source's effective trust tier until a human dismisses them.
- FR-16.6 A cost-of-application estimator returns an estimate band with a currency and a disclaimer that prices change.

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
