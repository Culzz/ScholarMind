# ScholarMind

**AI-powered scholarship discovery, eligibility intelligence, and application planning for African students.**

ScholarMind is not a chatbot wrapped around a search box. It is a source-grounded decision-support
system: scholarship facts live in a structured, auditable database; every material claim traces to an
official source, a snapshot version, and a check timestamp; and eligibility is decided by explicit
rules — with *unknown* treated as a first-class answer.

Target intake: **2027 postgraduate cycles**.

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

## Repository map

```
scholarmind/
├── apps/web/            React + TypeScript + Vite + Tailwind frontend
├── services/api/        FastAPI service (routers, schemas, orchestration)
├── services/worker/     Celery worker + beat schedule
├── scholarmind/         Framework-free core: ingestion, extraction, normalization,
│                        eligibility, retrieval, generation, freshness, evaluation, reporting
├── data/manifests/      Source manifest (allowlisted official URLs, trust tiers, cadences)
├── data/fixtures/eval/  Gold evaluation items
├── research/            Evaluation harness, experiment runs, paper assets
├── infra/               Dockerfiles + docker-compose
└── docs/                SRS, ARCHITECTURE, DATA_DICTIONARY, EVALUATION, SECURITY,
                         MODEL_CARD, DEPLOYMENT
```

## Core design rule

> The LLM is **not** the authority on scholarship facts.

The database and explicit rules decide eligibility, deadlines, funding components, cycle status and
reminders. Retrieval and the LLM interpret source text, explain results and summarise evidence —
with citation validation and abstention built in. A missing profile fact yields `unknown`, never
`satisfied`.

## Quick start

```bash
cp .env.example .env                     # add provider keys
docker compose -f infra/docker-compose.yml up -d db redis
pip install -r services/api/requirements.txt
alembic upgrade head
python -m scholarmind.ingestion.seed --manifest data/manifests/nigeria_v1.yaml
uvicorn services.api.app.main:app --reload
celery -A services.worker.celery_app worker -l info

cd apps/web && npm ci && npm run dev
```

Health: `GET /api/v1/health`

## Evaluation

```bash
python -m research.evaluation.harness.runner --experiment A --split dev --dataset data/fixtures/eval/dev.jsonl
```

Results are written to `research/experiments/<exp_id>/<timestamp>/results.json` with the dataset
version, split, config, model ids and code commit — every published number must come from one of
these files.

See `docs/EVALUATION.md` for the full protocol.

## Status

Phases 01–05 of the build plan are implemented, with the catalogue, planner and
intelligence layers in place:

| Area | What exists today |
|---|---|
| Schema | 37 tables across three Alembic migrations (core, platform, Part II) with pgvector, `tsvector` GIN and HNSW indexes |
| API | 22 endpoints: catalogue, eligibility, unlock paths, smart questions, assistant, compare, recommendations, planner + exports, change feed, admin console, health |
| Core | Framework-free domain package: ingestion, extraction, normalization, eligibility, retrieval, generation + verification, freshness, planning, readiness, vault, reporting |
| Worker | Celery app with hourly refresh, staleness sweep, alert dispatch, retry schedule and idempotent tasks |
| Frontend | React + TS + Vite + Tailwind app with claim-state language, discovery, detail, eligibility, compare, planner, assistant, dashboard |
| Evaluation | Offline harness, 202 passing tests including property-based invariants, ScholarBench-Africa bench (98 items), adversarial suite, redaction and publish tooling, CI regression gate |
| Research | Evaluation protocol, data dictionary, system card with placeholder metrics (no number is published until measured) |

**Not yet done:** live corpus capture (the corpus is still empty — the manifest and pipeline exist, the sources have not been ingested), the extraction worker stage, the auth/registration flow, and the measured evaluation results.

Metrics in `docs/MODEL_CARD.md` remain placeholders until the evaluation runs produce them.

## Documentation

- `PLAN.md` — the master blueprint (locked decisions, capability spine, release plan, risks)
- `docs/SRS.md` — requirements and acceptance criteria
- `docs/ARCHITECTURE.md` — system design, retrieval, generation, eligibility engine, ADRs
- `docs/DATA_DICTIONARY.md` — full schema
- `docs/EVALUATION.md` — datasets, baselines, metrics, release gates
- `docs/SECURITY.md` — threat model and controls
- `docs/MODEL_CARD.md` — intended use, results, limitations, failure modes
- `docs/DEPLOYMENT.md` — environments, CI/CD, observability, rollback
