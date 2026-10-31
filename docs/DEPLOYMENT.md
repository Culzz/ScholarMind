# Deployment

ScholarMind ships as a Docker Compose stack: Postgres (pgvector), Redis, the
FastAPI backend, the React SPA behind nginx, an optional Celery worker, and
one-shot `migrate` / `seed` containers. Nothing in the stack requires an LLM
key; when the key is added it slots into `.env` and the assistant / rule
drafting come up on their own.

## Quick start

```bash
cd infra
docker compose up -d db redis
docker compose up migrate          # runs alembic to head
docker compose up -d api web       # api on :8000, SPA on :5173 (proxies /api)
```

The SPA is served on one origin with the API (`/api/v1` → `api:8000`), so the
httpOnly refresh cookie stays first-party. No `VITE_API_BASE_URL` pointing at a
foreign host is supported by the image (the nginx proxy is the intended path).

## Seeded demo corpus

The demo corpus (verified captures of real scholarship pages, ~20 MB,
policies-respecting sources only) is imported by the `seed` profile:

```bash
docker compose --profile seed up seed
```

After it completes, `GET /api/v1/scholarships?limit=3` returns real records.
The seed step is honest and auditable: the builder prints what it imported,
flagged for review, and refused. Sources that are bot-blocked or partially
captured (Oxford, Cambridge, Edinburgh, Commonwealth partial, SETU/SETD, AKU,
UNILAG, Fulbright) stay labelled `needs_review` / manual-verification-only —
they are never presented as verified.

## The Celery worker (optional)

Scheduling/crawl tasks need Redis + the worker:

```bash
docker compose --profile full up -d worker
```

The demo runs fine without it; freshness checks then happen at build time only.

## LLM key (OpenAI)

When you have the OpenAI key, put it in `.env` at the repo root — API and
worker read it through `env_file`:

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

- Without a key everything still runs: the assistant abstains explicitly
  ("not configured with a language model in this environment") and the rule
  drafter refuses with `exit 2` — no fabricated rules, ever.
- With the key, LLM-proposed eligibility rules only enter the
  **propose-then-review queue** (`rule_candidates`, `status='drafted'`); the
  eligibility engine runs only on rules a human approved
  (`authored_by='human'`).
- `POST /api/v1/auth/register` always creates a student; promote an admin
  through the docs or SQL for the review queue at `/api/v1/admin/rule-candidates`.

## Local (no Docker)

```bash
# Postgres on 55432, migrations at repo root
$env:DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:55432/scholarmind"
$env:PYTHONPATH   = ".;services/api"
python -m alembic upgrade head
python scripts/rebuild_corpus.py --yes
python -m pytest tests -q -p no:warnings
uvicorn app.main:app --port 8000        # from services/api, or set PYTHONPATH as above
```

## Health & provenance

- `GET /api/v1/health` — liveness.
- `GET /api/v1/ready` — DB/Redis reachability.
- Every response carries the freshness state of the facts it serves; degraded
  and unknown states are named as such, never hidden behind scores.

## Verified / not yet verified

- Compose file: `docker compose config` passes (compose 29.6.2).
- Image builds and an end-to-end `up` have not been run yet — Docker Desktop
  was not running when this was written. First `docker compose up` is a live
  check; report anything that fails.
