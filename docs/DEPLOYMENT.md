# ScholarMind — Deployment & Operations

**Version:** 1.0 · Targets: local (docker-compose) → staging → production

---

## 1. Environments

| | Local | Staging | Production |
|---|---|---|---|
| Frontend | `vite dev` | build + preview (or Vercel preview) | Vercel / static CDN |
| API | uvicorn in Docker | Docker on Railway/Fly | Docker, ≥2 replicas |
| Worker | Celery worker + beat | Docker | Docker, separate service |
| DB | Postgres 16 (pgvector) in compose | managed Postgres (seeded subset) | managed Postgres (PITR) |
| Redis | Redis in compose | managed Redis | managed Redis |
| Corpus | seeded from `data/manifests` | full corpus | full corpus |
| Secrets | `.env` | CI secrets | provider secret store |

Data residency: production data lives in the managed Postgres region chosen for the target audience (EU or US), stated publicly.

---

## 2. Local setup

```bash
git clone <repo> && cd scholarmind
cp .env.example .env            # fill in provider keys
docker compose -f infra/docker-compose.yml up -d db redis
# install deps
python -m venv .venv && . .venv/Scripts/Activate   # Windows
pip install -e services/api -r services/api/requirements.txt
alembic upgrade head
python -m scholarmind.ingestion.seed --manifest data/manifests/nigeria_v1.yaml
celery -A services.worker.celery_app worker -l info
uvicorn services.api.app.main:app --reload
```

Frontend:
```bash
cd apps/web && npm ci && npm run dev
```

Health check: `GET http://localhost:8000/api/v1/health` → `{"status":"ok","db":"ok","redis":"ok","worker":"ok"}`.

---

## 3. Container images

Two images from one repo:
- `infra/Dockerfile.api` — FastAPI app, non-root user, `uvicorn` on port 8000, `HEALTHCHECK` hitting `/api/v1/health`.
- `infra/Dockerfile.worker` — Celery worker + beat, same dependency set as the API.

Build principles: multi-stage builds, pinned base image digests, no dev dependencies in the runtime image,
`PYTHONUNBUFFERED=1`, non-root user, read-only root filesystem where possible, `.dockerignore` excluding
`.venv`, `node_modules`, `.git`, `data/fixtures`.

---

## 4. Deployment order (each production release)
1. **Migrate** — `alembic upgrade head` as a one-off release task (never on app boot).
2. **Deploy API** — rolling; `/api/v1/health` gate.
3. **Deploy Worker** — after API is healthy (avoids workers processing before schema is live).
4. **Deploy frontend** — static assets; cache-busted.
5. **Smoke test** — scripted checks: list scholarships, fetch one detail, run one eligibility evaluation,
   ask one assistant question, create one application task.
6. **Rollback** — previous image tag + `alembic downgrade <rev>` if the migration is reversible
   (forward-fix preferred when migrations are not safely reversible).

---

## 5. Environment variables

See `.env.example` for the full list with defaults. Critical ones:

| Variable | Purpose | Secret |
|---|---|---|
| `DATABASE_URL` | Postgres connection | yes |
| `REDIS_URL` | Broker/cache | yes |
| `LLM_API_KEY` | Generation/extraction provider | yes |
| `EMBEDDING_API_KEY` | Embedding provider | yes |
| `LLM_MODEL` / `EMBEDDING_MODEL` | Pinned model ids | no |
| `CORS_ORIGINS` | Allowed frontend origins | no |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | Token signing | yes |
| `ADMIN_EMAILS` | Bootstrap admin accounts | no |
| `INGESTION_ENABLED` | Master switch for scheduled fetching | no |
| `SENTRY_DSN` | Error tracking | yes |
| `LOG_LEVEL` | Logging verbosity | no |

---

## 6. Scheduled jobs

| Job | Schedule | Notes |
|---|---|---|
| `refresh_sources` | hourly | Selects due sources by cadence |
| `staleness_sweep` | daily 03:00 UTC | Marks records stale; refreshes dashboard counters |
| `dispatch_alerts` | every 15 min | Opt-in channels only; dedupe by (alert_id, event_id) |
| `retry_failed_ingestion` | daily | Re-queues dead jobs below the attempt ceiling |
| `run_benchmark` | weekly (off-peak) | Optional; CI smoke variant is faster |
| `db_vacuum_analyze` | weekly | Via provider tooling |

Scheduling lives in Celery beat (or the platform scheduler if migrated). **A beat instance must be a
single active replica** — otherwise duplicate jobs. Idempotency keys prevent duplicate effects.

---

## 7. Observability

- **Logs:** structured JSON to stdout, shipped by the platform. Fields: `ts`, `level`, `request_id`,
  `route`, `status`, `latency_ms`, `user_id` (hashed), `component`. No PII, no tokens.
- **Metrics (recommended):** request rate/latency by route, assistant query count + abstain rate,
  ingestion success/failure by source, snapshot count, change events by severity, open conflicts,
  queue depth and oldest task age.
- **Health:** `/api/v1/health` (liveness + dependency checks), `/api/v1/health/ready` (readiness: DB
  reachable, schema at expected revision, worker heartbeat within 5 min).
- **Alerts:** ingestion failure streak, worker heartbeat missing, error rate > 2% over 15 min, assistant
  cost anomaly, DB connection saturation, backup failure.
- **Tracing:** optional OpenTelemetry spans per request (retrieval, generation, validation).

---

## 8. Backups & restore
- Managed Postgres: daily automated snapshots + point-in-time recovery (7–14 day window).
- Restore rehearsal: at least once per release in staging — restore to a new instance, run
  `alembic current`, smoke-test, record the result in the release notes.
- Snapshots of source pages live in `source_snapshots` and can be re-extracted, so a lost corpus is
  recoverable from the raw captures (this is the strongest argument for keeping `raw_content`).

---

## 9. Scaling path
1. **Read scaling:** Postgres read replicas; cache hot catalogue queries in Redis (short TTL, invalidated
   on corpus write).
2. **Ingestion scaling:** split the worker into per-region queues; raise per-host concurrency within
   courtesy limits.
3. **Retrieval scaling:** if measured p95 retrieval > 1.5 s, move dense search to a dedicated pgvector
   instance (still Postgres) before considering a separate engine.
4. **Service split:** extract the assistant/generation path only if load or isolation demands it —
   it is the most self-contained candidate because it has a clean interface (`generation/`).

---

## 10. Rollback procedure
1. Identify the regression (metrics, logs, user reports).
2. If caused by a bad deployment → redeploy the previous image tag (frontend and API independently).
3. If caused by a bad data migration → forward-fix with a corrective migration (preferred) or `alembic downgrade`
   when reversible.
4. If caused by bad ingested data → set the affected `source_documents.is_enabled = false`, re-run the
   affected extraction with the previous extractor version, and mark affected records `stale` (never delete history).
5. Communicate to users if any deadline or eligibility fact changed — a student-facing notice is
   safety-critical for this domain.

---

## 11. Release checklist
- [ ] Tests green (unit, integration, architecture purity, security checks).
- [ ] Held-out evaluation re-run if prompts/rules/models changed; results recorded.
- [ ] Migrations applied and reversible (or forward-fix documented).
- [ ] Environment variables added to the platform secret store.
- [ ] Health and readiness green in staging.
- [ ] Smoke test script passes.
- [ ] Backup verified before the migration.
- [ ] Rollback path identified and rehearsed.
- [ ] Docs updated (data dictionary, model card, changelog).
- [ ] Post-deploy monitoring watched for 30 minutes.

---

## 12. CI (`.github/workflows/`)
| Workflow | Triggers | Runs |
|---|---|---|
| `lint.yml` | push, PR | ruff, eslint, tsc, prettier check |
| `test.yml` | push, PR | pytest (unit + integration with a Postgres service), vitest, Playwright smoke |
| `eval-smoke.yml` | PR, nightly | 20-item dev subset of the eval harness; prints metrics as a comment |
| `docker.yml` | main | build + push images, run a container health check |
| `secret-scan.yml` | push | high-entropy scan, `.env` presence check |
| `migrate-check.yml` | PR | `alembic upgrade head` then `downgrade -1` on a throwaway DB |

CI must fail if the core package imports a framework or vendor SDK (architecture purity test).
