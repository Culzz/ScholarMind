# Status after the Phase 1 trust/security review

This page is the honest ledger for the fifteen findings in the review brief. A finding is only
`fixed` when the behaviour is implemented, covered by a test, and exercised against the local
Postgres corpus. "Verified" means it was run in this checkout, not that it is deployed.

The propose-then-review rule pipeline is now in place. Neither the LLM nor the regex extractor
may decide eligibility: the LLM drafts structured rule candidates (`drafted_by='llm'`), the regex
extractor drafts its own (`drafted_by='regex'`), and **only candidates a reviewer approves reach
the eligibility engine**, written with `authored_by='human'`.

The mechanism, with tests:

- `scholarmind/extraction/rule_drafter.py` — prompt builder + mechanical validator. A candidate is
  rejected unless its quote exists in the source text (the span is located by the validator, never
  produced by the model), and every claimed value literally appears inside that quote, and the
  kind/subject/operator match what the engine can evaluate.
- Table `rule_candidates` (migration `0006_rule_queue`) — status `proposed → approved/rejected`,
  drafted_by, model_id, reviewer fields, unique key so the same claim is not queued twice.
- `/admin/rule-candidates` (GET list, POST `{id}/approve` with optional edits, POST `{id}/reject`),
  admin-only; approval re-validates (including reviewer edits) and refuses invalid candidates with
  the validator's reasons. See `tests/api/test_rule_review.py`.
- CLI: `python -m app.cli draft-rules [--limit N] [--dry-run]` runs the LLM pass (refuses to run
  without `LLM_API_KEY`), and `review-rules --list | --approve ID | --reject ID` for review.
- The corpus builder routes regex-extracted eligibility facts into the queue instead of writing
  rules; shape problems (e.g. the extractor's `language` kind) are stored as `validation_notes`
  for the reviewer instead of silently dropping the candidate.

**The real corpus currently queues 0 candidates** — the regex extractor finds nothing promotable
on the captured pages, and the LLM pass needs an API key (not yet configured). The next corpus
(the expanded 100+-opportunity set) is where this pipeline pays off, because every rule approved
in review becomes a labelled gold item for the eval harness as a by-product.

## Findings

| # | Finding | Status | Where | Evidence |
|---|---|---|---|---|
| 1 | `/auth/refresh` never read the refresh cookie | fixed | `services/api/app/api/v1/auth.py` | `tests/api/test_auth_flow.py::test_refresh_rotates_the_cookie` |
| 2 | Chunks stored `char_start=0, char_end=len(chunk)`, so citations pointed at the page start | fixed | `scholarmind/retrieval/fusion.py`, `services/worker/tasks/pipeline.py`, `corpus_builder.py` | `tests/unit/test_retrieval_spans.py`; pipeline asserts `text[start:end] == chunk.text` before insert |
| 3 | Embeddings were never stored although retrieval advertised hybrid | fixed | `pipeline._embed_chunks` | 0 vectors with no provider, real vectors when `EMBEDDING_API_KEY` is set; dimension checked |
| 4 | Freshness inferred from `trust_tier == "stale"` | fixed | `source_documents.freshness_state`, retrieval, assistant | `source_freshness_state` in the catalogue/detail; separate assistant warnings |
| 5 | Fetch failure conflated with freshness/staleness | fixed | `services/worker/tasks/ingest.py` | `fetch_status` (attempt outcome) and `freshness_state` (`fresh`/`stale`/`failed`) are written independently; sweep no longer rewrites `fetch_status` |
| 6 | Lexical-only runs reported as `hybrid` | fixed | `services/api/app/services/retrieval.py` | `mode_requested` / `mode_used` / `degraded_reason`; `tests/unit/test_retrieval_modes.py` |
| 7 | Dense search silently skipped wrong-dimension vectors | fixed | `retrieval._dense_query` | raises `ValueError`; covered by the same test file |
| 8 | Broad `except Exception` swallowed database errors | fixed | `pipeline.py`, `ingest.py` | bookkeeping failures now raise; only genuinely expected outcomes return a result |
| 9 | Re-running extraction duplicated chunks and claims | fixed | migration `0005_foundation`, both writers | unique `(snapshot_id, content_hash)` and `(snapshot_id, claim_type, span_start, span_end)` + `ON CONFLICT` |
| 10 | Eval stub echoed the gold ids, reporting perfect recall | fixed | `research/evaluation/harness/runner.py` | refuses unlabelled items; `--smoke` output is marked `measurement_valid: false` |
| 11 | CI gate passed when it found no results | fixed | `research/evaluation/gate.py` | exits 2 on missing/empty/stub/invalid/zero-item results; missing metric fails |
| 12 | Registration granted admin from `ADMIN_EMAILS` | fixed | `auth.register`, `services/api/app/cli.py` | registration always `student`; `python -m app.cli create-admin` |
| 13 | Refresh tokens were unrevocable and unrotated | fixed | `refresh_tokens` table, `auth.refresh` | family rotation; replaying a rotated token revokes the family |
| 14 | No rate limiting on auth/assistant/write routes | fixed | `services/api/app/core/rate_limit.py` | auth routes, assistant (per minute and per day), eligibility and planning writes are limited per client; `tests/unit/test_rate_limit_csrf.py` |
| 15 | SSRF: ports 8080/8443 allowed, DNS re-resolved after validation | fixed | `scholarmind/ingestion/pinned_client.py`, `safety.py` | connection pinned to the validated address, SNI/Host preserved; only 80/443 |

Also fixed while in this area (not in the fifteen):

- Cross-site request protection for cookie endpoints (`SameSite=Lax` + Origin allow-list,
  `app/core/csrf.py`), tested.
- `CORS_ALLOWED_ORIGINS` in `.env.example` never reached `settings.cors_origins`; a deployment
  would have silently kept the localhost default. Renamed to `CORS_ORIGINS`.
- PDFs are refused until a PDF text extractor exists; a captured PDF had been indexed as binary.
- Programme grouping: manifest roots can share a `group`, so Chevening is one award rather than
  three. The crawler already captured each URL once (`4ab211a`).
- Deadline selection rejects offer/interview dates instead of falling back to them, and opening
  dates are no longer extracted as deadlines.

## Corpus after a clean rebuild

Values verified against the database after `scripts/rebuild_corpus.py --yes` over the capture in
`data/raw/` (2026-10-29), not from build counters:

| Metric | Value |
|---|---|
| Manifest sources | 99 (72 source documents with a captured page) |
| Snapshots imported | 72 |
| Scholarships | **18** |
| Cycles | 18 (4 with a deadline) |
| Evidence chunks | 320 |
| Confirmed claims | 11 |
| Funding components | 36 |
| Required documents | 8 |
| Approved eligibility rules | **0** |
| Rule candidates in the queue | 0 |
| Source rows claiming `ok` without a snapshot | **0** |

`pytest tests` passes **300** tests in this checkout.

The scholarship count dropped from 27 to 18 because nine records stood on
**failed captures** (Oxford 403, Cambridge 403, Edinburgh 403, Fulbright 403,
NDDC 403, SETD/UNILAG/AKU unresolvable, Commonwealth timeout). The builder used
to create a scholarship and a `fetch_status='ok'` source row for a page it
could never read, then skip the content - a fabricated record. A failed capture
is now kept out of the corpus entirely: it is listed explicitly in the build
warnings (`failed capture kept out of the corpus (no record is created)`), and
the corresponding manifest entries carry `fetch_policy: browser` (headless
adapter) or `fetch_policy: manual` (entered by hand with provenance only).
`due_sources` never schedules a `manual` entry; the capture step refuses to
fetch one. See `tests/unit/test_fetch_policy.py` and
`tests/api/test_corpus_builder.py`.

## Known gaps

- **The rule queue is empty on the real corpus.** The propose-then-review pipeline is wired and
  tested, but the regex extractor finds no promotable candidates on the captured pages and the LLM
  pass needs an API key that is not configured yet. Every real scholarship therefore reports
  `unknown` requirements, honestly. Expanding the corpus and running the LLM drafter with human
  review is the next work item, and approvals build the gold set for measuring rule extraction.
- **Chevening eligibility pages are JS-rendered.** Playwright is not installed, so those pages
  are captured as navigation only; the deadline is genuinely absent and is reported as unknown.
- **Rate limiting is in-process** and keyed by client address. A multi-instance deployment needs
  Redis counters, and an authenticated user behind a shared NAT shares the budget with others.
- **Deadline attribution is heuristic.** Offer dates are now rejected, but a page that lists
  several programmes' dates (UCT key dates) resolves to the first qualifying closing date.
- **Some sources are unreachable** (DNS/timeout/403): Oxford, Cambridge, Edinburgh, Commonwealth
  (partial), SETU/SETD, AKU, UNILAG, Fulbright.
- **No measured evaluation numbers.** The benchmark items are unverified templates without gold
  evidence ids, the runner refuses them, and the gate fails when there is no valid run. That is
  deliberate: there is nothing publishable yet.

## Rebuild and verify

```powershell
$env:DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55432/scholarmind'
$env:PYTHONPATH='.;services/api'
python -m alembic upgrade head
python scripts/rebuild_corpus.py --yes
python -m pytest tests -q
python scripts/smoke_retrieval.py

# the rule draft/review loop (needs LLM_API_KEY for drafting):
python -m app.cli draft-rules --dry-run       # report without writing
python -m app.cli draft-rules --limit 40
python -m app.cli review-rules --list
python -m app.cli review-rules --approve <candidate_id> --note "checks out on the page"
python scripts/smoke_retrieval.py
```

## API contract wiring (deployed shape, verified in this checkout)

The SPA's contract is now served by the API; every surface was exercised
against the rebuilt local corpus via `scripts/_contract_check.py` and the new
test module `tests/api/test_contract_surfaces.py`:

- `GET /scholarships` — cursor pagination (`next_cursor`, opaque base64 offset),
  items carry `current_cycle` in the full SRS cycle shape (with `claim_state`
  derived from `status_confidence`/`freshness_state`, never invented),
  `official_url`, `description`, `rule_count`, `provider_country_iso3`,
  `deadline_claim_state`.
- `GET /scholarships/{id}` — the SPA envelope  `{scholarship, cycles, funding_components, required_documents, rules,
  sources, latest_assessment}`; `latest_assessment` is `null` until a stored
  assessment feature ships. History/evidence use the SPA field names
  (`field_name`, `claim_text`, `snapshot_id`).
- `GET/PUT /profile` over `student_profiles`; `completeness` counts usable
  fields, is never presented as eligibility, and unknown fields are rejected
  (`extra='forbid'`).
- `GET/POST/PATCH /applications`, `GET /tasks`, `PATCH /tasks/{id}` — creating
  an application generates its checklist from the deterministic planner
  (`is_auto_generated=true`, `status='todo'`); `completed_at` tracks the task's
  new state; status vocabularies match the SPA.
- `POST /eligibility/evaluate` — no selection evaluates **all current cycles**
  (bounded at 50, deadlines first) instead of 404; each assessment carries
  `verdict_counts` next to `counts` (same numbers, no percentage, plus
  `profile_hash` and a stable `id`).
- `POST /eligibility/explain` — returns `trace` with `rule_id` per result.
- `GET /recommendations` — items now serve the SPA contract (`rank`, full
  `scholarship`, `cycle` with `claim_state`, `factors` as labelled
  `{key,label,value,weight,contribution,detail}` rows, `notes`); the score
  stays labelled a prioritisation aid.
- `POST /assistant/ask` — the persisted audit id and `created_at` are returned
  (early abstentions legitimately have neither; the UI says so).

Test state: `pytest tests -q` → **295 passed, 0 failures**; web `typecheck` +
13 vitest tests + production build green.

## Deployment

`infra/docker-compose.yml` boots db+redis+migrate+api+web (+ optional worker),
`infra/Dockerfile.web` + `apps/web/nginx.conf` serve the SPA and proxy `/api`
on one origin (first-party refresh cookie). Seeded demo: `docker compose
--profile seed up seed` imports the verified capture set. See
`docs/DEPLOYMENT.md`. The OpenAI path is keyed and waiting: set
`LLM_PROVIDER=openai`, `LLM_API_KEY`, `LLM_BASE_URL=https://api.openai.com/v1`,
`LLM_MODEL=gpt-4o-mini` in `.env`; without a key the assistant abstains
explicitly and drafting refuses with exit 2 — nothing fabricated.

Verified so far: `docker compose ... config` validates (compose CLI 29.6.2).
The image builds and `up` were **not exercised locally** — the Docker Desktop
daemon was not running at commit time — so the first `docker compose up` is
still a live check, not a repeat of a recorded pass.
