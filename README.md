# ScholarMind

**AI-powered scholarship discovery, eligibility intelligence, and application planning for African students.**

ScholarMind is not a chatbot wrapped around a search box. It is a source-grounded decision-support
system: scholarship facts live in a structured, auditable database; every material claim traces to an
official source, a snapshot version, and a check timestamp; and eligibility is decided by explicit
rules — with *unknown* treated as a first-class answer.

Target intake: **2027 postgraduate cycles**, Nigeria-first.

---

## What it does

| Question | How ScholarMind answers it |
|---|---|
| What can I apply for? | Hybrid retrieval over a versioned corpus of official sources, with structured filters |
| Am I eligible? | Rule-by-rule verdicts: `satisfied` / `not_satisfied` / `unknown` / `needs_review`, each with a reason and evidence |
| What is actually open? | Cycles stored separately from awards, with deadlines, opening dates, status and freshness |
| How competitive am I? | Transparent factor breakdown — never a probability of success |
| What should I do next? | Deadline-aware, document-aware application plan with dependencies and reminders |
| Can I trust this? | Evidence ledger, contradiction detector, conflict surfacing, and honest abstention |

## Project status

Everything below runs against a real local PostgreSQL database populated from really captured
pages — not fixtures.

| Area | State |
|---|---|
| Schema | 42 tables across 6 Alembic migrations; `pgvector` is optional (float-array fallback), `tsvector` column + GIN index for lexical search |
| Corpus | 99 allowlisted sources, 72 captured snapshots: 27 scholarships, 18 cycles (4 with a deadline), 320 evidence chunks, 11 confirmed claims, 36 funding components, 8 required documents, 0 eligibility rules in the engine |
| Rule pipeline | propose-then-review: LLM and regex drafters propose candidates into a queue; a mechanical validator rejects spans/values that don't match the source; only rules a human approves (`authored_by='human'`) run in the eligibility engine |
| Retrieval | Lexical search with query-term coverage boosting + RRF fusion + per-document diversity cap; `mode_used` names a lexical fallback; aggregator-tier pages never returned as evidence |
| Auth | Short-lived JWTs; refresh tokens stored as hashes in Postgres with family rotation and replay revocation; `SameSite=Lax` + Origin allow-list; per-client rate limits; admins only via `python -m app.cli create-admin` |
| API | Catalogue, detail, history, evidence, eligibility evaluate/explain/unlock/questions, assistant, compare, recommendations, planner + exports, change feed, auth, admin, health |
| Core | Framework-free package: ingestion, text extraction, extraction, normalization, eligibility, retrieval, generation + verification, freshness, planning, readiness, vault, reporting |
| Tests | 284 passing (`pytest tests -q`), including property-based invariants, core-purity checks, and database-backed auth/rotation and rule-queue tests |
| Frontend | React + TypeScript + Vite + Tailwind scaffold (57 files): discovery, detail, eligibility, compare, planner, assistant |
| Evaluation | Offline harness, ScholarBench-Africa (98 unverified template items), CI regression gate that fails without a valid run — **no metrics published yet** |

### Verified in this checkout

```bash
pytest tests -q                                   # 284 passed
python scripts/smoke_api.py                       # live API against the populated database
python scripts/smoke_retrieval.py                 # real lexical retrieval over 320 chunks
python scripts/rebuild_corpus.py --yes            # clean rebuild from data/raw
python scripts/compare_extraction.py              # extraction quality: old vs. new text pipeline

# draft + review eligibility rules (drafting needs LLM_API_KEY):
python -m app.cli draft-rules --dry-run            # report without writing
python -m app.cli draft-rules                       # propose candidates into the queue
python -m app.cli review-rules --list
python -m app.cli review-rules --approve <id>       # validation runs again at approval
```

`scripts/smoke_api.py` currently reports: health and readiness OK, 27 scholarships listed,
detail + evidence served, eligibility evaluated, and the assistant abstaining with zero citations
when no model is configured (the intended behaviour).

`docs/STATUS.md` is the finding-by-finding ledger for the Phase 1 trust/security review.

### Not done yet

- **The rule queue is empty on the real corpus.** The propose-then-review pipeline is wired and
  tested (validator, admin API, CLI), but the regex extractor finds no promotable candidates on
  the captured pages and the LLM drafting pass needs an `LLM_API_KEY` that isn't configured yet.
  Every real scholarship therefore reports `unknown` requirements. Expanding the corpus to 100+
  well-reviewed opportunities and running the draft/review loop is the headline work item — every
  approved rule is also a gold label for the evaluation harness.
- **Chevening eligibility pages are JS-rendered.** Playwright is not installed, so those pages
  are captured as navigation only; the deadline is genuinely absent and stays `unknown` rather
  than being guessed.
- **Deadline attribution is heuristic.** Offer and interview dates are rejected, but a page that
  lists several programmes' dates resolves to the first qualifying closing date.
- **PDF pages are not ingested.** The fetcher refuses `application/pdf` because no extractor
  exists; a captured PDF is skipped instead of indexed as binary.
- **Rate limiting is in-process**, so a multi-instance deployment needs Redis counters.
- **No measured evaluation numbers.** The benchmark items are unverified templates without gold
  evidence ids; the runner refuses them and the gate fails when there is no valid run.
- **Some sources are unreachable** (DNS/timeout/403): Oxford, Cambridge, Edinburgh, Commonwealth
  (partial), SETU/SETD, AKU, UNILAG, Fulbright.

## Repository map

```
scholarmind/
  apps/web/            React + TypeScript + Vite + Tailwind frontend
  services/api/        FastAPI service (routers, schemas, services, migrations)
  services/worker/     Celery worker + beat schedule
  scholarmind/         Framework-free core: ingestion, extraction, normalization,
                       eligibility, retrieval, generation, freshness, evaluation, reporting
  data/manifests/      Source manifest (allowlisted URLs, trust tiers, fetch policy, cadence)
  data/raw/            Captured pages (page.html, page.txt, capture.json) — not committed
  data/fixtures/eval/  Gold evaluation items
  scripts/             Operational checks: corpus build, re-extraction, retrieval and API smoke tests
  research/            Evaluation harness, experiment runs, paper assets
  infra/               Dockerfiles + docker-compose
  docs/                SRS, ARCHITECTURE, DATA_DICTIONARY, EVALUATION, SECURITY,
                       MODEL_CARD, DEPLOYMENT, CORPUS_CAPTURE
```

## Core design rule

> The LLM is **not** the authority on scholarship facts.

The database and explicit rules decide eligibility, deadlines, funding components, cycle status and
reminders. Retrieval and the LLM interpret source text, explain results and summarise evidence —
with citation validation and abstention built in. A missing profile fact yields `unknown`, never
`satisfied`. Aggregator-tier sources are never the evidence behind a confirmed fact.

## Quick start

```bash
cp .env.example .env                     # add provider keys (optional for local work)
docker compose -f infra/docker-compose.yml up -d db redis
pip install -r services/api/requirements.txt
alembic upgrade head
uvicorn services.api.app.main:app --reload
celery -A services.worker.celery_app worker -l info
cd apps/web && npm ci && npm run dev
```

Health: `GET /api/v1/health`

### Building the corpus (no Docker required)

The pipeline is three independently runnable steps. Each writes to disk first, so a failed build
never corrupts the database.

```bash
# 1. Capture the allowlisted sources (courtesy delay, SSRF guard, TLS never weakened)
python -m scholarmind.ingestion.capture --manifest data/manifests/nigeria_v1.yaml --crawl-depth 4

# 2. Re-extract page text from the stored HTML (no network) after improving the extractor
python scripts/renormalize_captures.py --captures data/raw

# 3. Load into PostgreSQL (clean rebuild; --yes deletes the previous corpus and
#    scholarship-linked student rows, then imports the capture)
DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55432/scholarmind \
  PYTHONPATH=".;services/api" python scripts/rebuild_corpus.py --yes --captures data/raw
```

The builder records provenance for every fact: source document, snapshot hash, character span, and
check timestamp. Claims that fail span validation are stored as ambiguous, never confirmed. Chunk,
claim and snapshot inserts carry unique keys, so re-running a build or a task does not duplicate
evidence.

Administrators are provisioned out-of-band, never through registration:

```bash
PYTHONPATH=".;services/api" python -m app.cli create-admin --email ops@example.org
```

See `docs/CORPUS_CAPTURE.md` for what the real sources actually return, including the JS-rendering
finding.

## Evaluation

```bash
python -m research.evaluation.harness.runner --experiment A --split dev \
  --dataset data/fixtures/eval/dev.jsonl
```

The runner refuses items without gold evidence ids, because a run over unlabelled templates cannot
measure recall. `--smoke` exercises the plumbing and marks the output `measurement_valid: false`;
the CI gate rejects it, along with missing, empty or stub results. Results are written to
`research/experiments/<exp_id>/<timestamp>/results.json` with the dataset version, split, config,
model ids and code commit — every published number must come from one of these files. See
`docs/EVALUATION.md` for the full protocol.

## Documentation

- `PLAN.md` — master blueprint (locked decisions, capability spine, release plan, risks)
- `docs/SRS.md` — requirements and acceptance criteria
- `docs/ARCHITECTURE.md` — system design, retrieval, generation, eligibility engine, ADRs
- `docs/DATA_DICTIONARY.md` — full schema
- `docs/EVALUATION.md` — datasets, baselines, metrics, release gates
- `docs/CORPUS_CAPTURE.md` — what the live sources return and how the corpus is built
- `docs/SECURITY.md` — threat model and controls
- `docs/MODEL_CARD.md` — intended use, results, limitations, failure modes
- `docs/DEPLOYMENT.md` — environments, CI/CD, observability, rollback
