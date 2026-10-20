# ScholarMind — Security & Privacy

**Version:** 1.0 · Owner: engineering · Applies to all environments

---

## 1. Threat model (summary)

| # | Threat | Impact | Mitigation |
|---|---|---|---|
| T1 | SSRF via source fetching | Internal network access | Host allowlist, DNS/IP validation pre- and post-redirect, private-range blocking, port restriction |
| T2 | Prompt injection in retrieved pages | Model follows attacker instructions, leaks context | Instruction isolation, structured output, no tool access from content, allowlisted sources, adversarial eval set |
| T3 | Cross-user data access | Profile/document disclosure | Owner-scoped queries in the repository layer, authz integration tests, no client-side filtering of user data |
| T4 | Hallucinated scholarship facts | Student harm (missed deadline, wrong eligibility) | Structured facts authoritative, evidence-bound claims, citation validation, abstention, claim-state UI |
| T5 | Secret leakage | Credential compromise | Env-only secrets, CI secret scan, no secrets in bundles/logs, rotation procedure |
| T6 | Scraping abuse / ToS violation | Blocked access, legal risk | Allowlisted manifest, courtesy rate limits, robots awareness, prefer official feeds/APIs, caching |
| T7 | PII exposure in logs/analytics | Privacy breach | Log redaction, no PII in request logs, minimised LLM payloads, retention limits |
| T8 | Denial of service via assistant abuse | Cost blow-up | Rate limits, token budgets, per-user daily quotas, caching |
| T9 | Untrusted file parsing (PDF) | Parser exploit | Size/type caps, sandboxed parsing container, no macro execution, patched base image |
| T10 | Data tampering by admin | Integrity loss | Audit trail on all admin mutations, least-privilege roles, backup restore rehearsal |

---

## 2. Authentication & authorisation

- Passwords hashed with Argon2id (fallback bcrypt with cost 12), per-user salts.
- JWT access token (15 min) + rotating refresh token (7 d) in `httpOnly`, `Secure`, `SameSite=Lax` cookies.
- Token revocation list for compromised sessions; "log out all devices".
- Optional Google OAuth (release 3+); accounts are linked by verified email.
- Roles: `student`, `admin`, `researcher`. Admin routers are mounted under `/api/v1/admin` with a
  dependency requiring the admin role; researcher role grants read-only access to evaluation artifacts.
- **Authorisation rule:** every user-scoped resource is fetched with an owner predicate in SQL
  (`WHERE id = :id AND user_id = :current_user`), never by fetching then filtering in Python.
- Rate limits: reads 240/min, writes 60/min, assistant 20/min + 200/day, refresh 5/min, export 10/min.

## 3. Secrets

- All secrets via environment variables / managed secret store; `.env` is git-ignored, `.env.example` is committed.
- CI step scans the tree for high-entropy strings and known key prefixes (`sk-`, `ghp_`, AWS keys).
- Rotations: LLM provider key quarterly and on suspected exposure; DB credentials on rotation via
  provider-managed secrets; documented runbook in `docs/DEPLOYMENT.md`.
- Frontend never receives service credentials; browser code contains only the public API base URL.

## 4. Fetching & ingestion hardening
- Domain allowlist per `data/manifests/*.yaml`; a URL outside the allowlist is refused, not fetched.
- Resolve hostname → validate IP is public (reject RFC1918, loopback, link-local, IPv6 ULA, metadata
  endpoint `169.254.169.254`) → re-validate after every redirect (max 3) → cap response size (5 MB) and content types (HTML, PDF, plain text) → 20 s timeout.
- Conditional requests (ETag/Last-Modified) to minimise load on official servers.
- Per-host concurrency limit (1) and minimum inter-request delay (≥ 5 s) as a courtesy default.
- PDFs parsed in an isolated worker with no network access and a 30 s CPU cap.
- Downloaded HTML is sanitised (script/style stripped, base URL rewritten) before storage.

## 5. LLM & prompt-injection defence
1. Retrieved content is inserted into a labelled evidence block; system instructions state that content is
   data and that any instruction inside it must be ignored and reported.
2. Retrieved content never grants capability: the model has no tools, no network, no file access.
3. Output is schema-validated; unexpected fields or types → repair attempt → abstain.
4. Only allowlisted, trust-tiered sources are retrieved for assistant answers; aggregator-tier sources are
   excluded by default.
5. Adversarial items in the evaluation set measure whether injection attempts alter behaviour; a
   regression here blocks release (see `docs/EVALUATION.md` §9).
6. Provider-side: zero-data-retention where available; no training on submitted data; PII minimised
   before sending (profile facts are reduced to the fields required for the question).

## 6. Data protection
- **Data classification:** Public (scholarship data) · Personal (profile, saved items, notes) · Sensitive
  (uploads, references) · Secret (credentials).
- Postgres: encrypted at rest (managed), TLS in transit, per-environment credentials, least-privilege
  app role (no DDL at runtime; migrations use a separate role).
- Sensitive columns may be encrypted at the application layer with a KMS-managed key (profile notes).
- Retention: personal data retained while the account is active; hard delete on request within 30 days;
  `answer_audits` de-identified and rolled after 24 months.
- User rights: export (JSON + Markdown) and delete endpoints, both covered by integration tests.
- Logs: request ids and timings only; no profile values, no raw documents, no auth tokens. Redaction
  middleware scrubs known sensitive keys.

## 7. Application security baseline
- Security headers: CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`.
- CORS restricted to the configured frontend origins.
- Input validation with Pydantic on every request; SQL exclusively via ORM/parameterised queries.
- File upload (future): magic-byte check, AV scan, size cap, stored outside the web root.
- Dependency scanning (Dependabot/OSV) and pinned base images in CI.

## 8. Operational security
- Least privilege: the worker uses a DB role without DDL; the admin app requires SSO (staff).
- Admin mutations are audit-logged with actor, target, before/after.
- Backups: daily snapshots + PITR; restore rehearsed at least once per release; restore results recorded.
- Secrets rotation runbook; on suspected compromise: revoke keys, rotate, purge caches, review audit log.
- Incident response: severity levels, a 24 h containment target for credential exposure, and a
  documented student-facing notice path (deadline changes are safety-critical for users).

## 9. Third-party data use
- Scholarship pages are public information; we store snapshots for provenance and change detection.
- We do not republish full page text publicly; excerpts are shown with attribution and links.
- No user profile data is shared with third parties. LLM providers receive only the minimal prompt
  payload needed for the question, per request.

## 10. Security test checklist (per release)
- [ ] Authz integration tests: every user-scoped endpoint rejects cross-account access.
- [ ] SSRF: requests to private IPs, `file://`, `169.254.169.254`, and redirect-to-private are blocked.
- [ ] Injection: adversarial eval items produce no behaviour change and no instruction echo.
- [ ] Rate limits enforced and returning 429 with `Retry-After`.
- [ ] Secret scan passes; no key in the client bundle (`grep` the built assets).
- [ ] Backup restore tested and result recorded.
- [ ] Headers verified in production (CSP, HSTS).
- [ ] Admin actions appear in the audit log.
