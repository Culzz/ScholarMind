# Status after the Phase 1 trust/security review

This page is the honest ledger for the fifteen findings in the review brief. A finding is only
`fixed` when the behaviour is implemented, covered by a test, and exercised against the local
Postgres corpus. "Verified" means it was run in this checkout, not that it is deployed.

Counts below come from `scripts/rebuild_corpus.py --yes` over the capture in `data/raw/`
(72 snapshots) and from `pytest tests` (261 tests). They are measurements of this checkout,
not claims about production.

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

| Metric | Value |
|---|---|
| Manifest sources | 99 |
| Snapshots imported | 72 |
| Scholarships | 27 |
| Cycles | 18 (5 with a deadline) |
| Evidence chunks | 320 |
| Confirmed claims | 11 |
| Funding components | 36 |
| Required documents | 8 |
| Eligibility rules | **0** |

The claim count is lower than the previous build (23) because earlier counters incremented per
attempt rather than per inserted row; 11 is the number of rows a reader can actually cite.

## Known gaps

- **Eligibility rules are empty on the real corpus.** The extractor finds nationality rules in
  fixtures, but no captured page yields a promotable rule. The eligibility engine is therefore
  exercised only by tests, and every real scholarship reports `unknown` requirements.
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
```
