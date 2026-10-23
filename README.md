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
| Schema | 40 tables across 4 Alembic migrations; `pgvector` is optional (float-array fallback), `tsvector` column + GIN index for lexical search |
| Corpus | 33 allowlisted sources captured (90 pages on disk); 76 source documents, 34 scholarships, 25 cycles, 392 evidence chunks, 23 confirmed claims, 50 funding components, 9 required documents |
| Retrieval | Lexical search with query-term coverage boosting + RRF fusion + per-document diversity cap; aggregator-tier pages never returned as evidence |
| API | Catalogue, detail, history, evidence, eligibility evaluate/explain/unlock/questions, assistant, compare, recommendations, planner + exports, change feed, auth, admin, health |
| Core | Framework-free package: ingestion, text extraction, extraction, normalization, eligibility, retrieval, generation + verification, freshness, planning, readiness, vault, reporting |
| Tests | 215 passing (`pytest tests -q`), including property-based invariants and core-purity checks |
| Frontend | React + TypeScript + Vite + Tailwind scaffold (57 files): discovery, detail, eligibility, compare, planner, assistant |
| Evaluation | Offline harness, ScholarBench-Africa (98 items), adversarial suite, CI regression gate — **no metrics published yet** |

### Verified in this checkout

```bash
pytest tests -q                                   # 215 passed
python scripts/smoke_api.py                       # live API against the populated database
python scripts/smoke_retrieval.py                 # real lexical retrieval over 392 chunks
python scripts/compare_extraction.py              # extraction quality: old vs. new text pipeline
```

`scripts/smoke_api.py` currently reports: health and readiness OK, 34 scholarships listed,
detail + evidence served, eligibility evaluated, and the assistant abstaining with zero citations
when no model is configured (the intended behaviour).

### Not done yet

- **Chevening eligibility pages are JS-rendered.** Playwright is not installed, so four of them are
  not captured; a plain fetch yields zero occurrences of "eligible" on the page. The render adapter
  (`scholarmind/ingestion/browser.py`) exists and is wired in, but is untested against the real site.
- **Crawl grouping is imperfect.** Child pages are captured more than once (the same URL can arrive
  under two different parents) and grandchildren are keyed under the intermediate page, so a few
  programmes appear as several scholarships (Chevening currently yields six rows instead of one).
- **Only 1 eligibility rule is stored.** The rule extractor covers nationality lists; work
  experience, residency and English-score rules are extracted as claims, not yet promoted to rules.
- **Deadline attribution needs care.** "Offer deadline" on a Chevening page is currently stored as
  the application deadline; section context is not yet used to qualify a date.
- **No measured evaluation numbers.** `docs/MODEL_CARD.md` metrics stay as placeholders until the
  harness runs against this corpus.
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

# 3. Load into PostgreSQL (idempotent)
DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55432/scholarmind \
  python -m services.api.app.services.corpus_builder \
  --manifest data/manifests/nigeria_v1.yaml --captures data/raw
```

The builder records provenance for every fact: source document, snapshot hash, character span, and
check timestamp. Claims that fail span validation are stored as ambiguous, never confirmed.

See `docs/CORPUS_CAPTURE.md` for what the real sources actually return, including the JS-rendering
finding.

## Evaluation

```bash
python -m research.evaluation.harness.runner --experiment A --split dev \
  --dataset data/fixtures/eval/dev.jsonl
```

Results are written to `research/experiments/<exp_id>/<timestamp>/results.json` with the dataset
version, split, config, model ids and code commit — every published number must come from one of
these files. See `docs/EVALUATION.md` for the full protocol.

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
