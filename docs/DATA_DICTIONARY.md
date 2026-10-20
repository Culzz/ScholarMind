# ScholarMind — Data Dictionary

**Version:** 1.0 · Schema for PostgreSQL 16 + pgvector
Conventions: `snake_case` tables; PK `id UUID` (v4 unless noted); `created_at/updated_at TIMESTAMPTZ`;
soft deletion only where history matters (`archived_at`); all timestamps UTC; money as
`NUMERIC(12,2)` with `currency CHAR(3)`; enums as `TEXT` + `CHECK` constraints (easier to extend
than native enums during a fast-moving schema).

---

## 1. Reference / vocabulary tables

### `countries`
| Column | Type | Notes |
|---|---|---|
| `iso3` | CHAR(3) PK | ISO 3166-1 alpha-3 |
| `name` | TEXT | Official short name |
| `region` | TEXT | `africa` / `europe` / `global` / other |
| `is_in_scope` | BOOL | African country in the platform's target scope |

### `fields_of_study`
| Column | Type | Notes |
|---|---|---|
| `code` | TEXT PK | Internal code, e.g. `ENG` |
| `name` | TEXT | Display name |
| `parent_code` | TEXT FK→fields_of_study | Hierarchical grouping |
| `aliases` | JSONB | Free-text synonyms used by normalization |

### `degree_levels`
| Column | Type | Notes |
|---|---|---|
| `code` | TEXT PK | `bachelors`, `masters`, `mba`, `phd`, `postdoc`, `research` |
| `name` | TEXT | |
| `ordinal` | INT | Sort order |

---

## 2. Core scholarship entities

### `scholarships`
Stable identity of an award, independent of any cycle.

| Column | Type | Constraints / Notes |
|---|---|---|
| `id` | UUID | PK |
| `slug` | TEXT | UNIQUE, URL-safe |
| `name` | TEXT | Official name |
| `provider_type` | TEXT | CHECK in (`government`, `university`, `foundation`, `ngo`, `corporate`, `multilateral`, `other`) |
| `provider_name` | TEXT | |
| `provider_country_iso3` | CHAR(3) | FK→countries |
| `description` | TEXT | Short curated summary (prose is fine here) |
| `study_levels` | JSONB | array of degree level codes |
| `fields_of_study` | JSONB | array of field codes |
| `destinations` | JSONB | array of {country_iso3, institution?, note?} |
| `canonical_source_id` | UUID | FK→source_documents — the authoritative page |
| `trust_tier` | TEXT | CHECK in (`official_primary`, `official_secondary`, `partner`, `aggregator`) |
| `website_url` | TEXT | |
| `status` | TEXT | CHECK in (`active`, `inactive`, `archived`) |
| `archived_at` | TIMESTAMPTZ | |
| `created_at/updated_at` | TIMESTAMPTZ | |

### `scholarship_cycles`
An application round. Dates, funding and rules belong here, not on `scholarships`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `scholarship_id` | UUID | FK→scholarships, NOT NULL |
| `intake_year` | INT | e.g. 2027 |
| `cycle_label` | TEXT | e.g. "2027 Postgraduate Scholarships" |
| `opens_at` | DATE | NULL if not yet announced |
| `opens_at_precision` | TEXT | CHECK in (`day`, `month`, `year`, `unknown`) |
| `deadline_at` | TIMESTAMPTZ | NULL if unknown |
| `deadline_timezone` | TEXT | e.g. `Europe/London` |
| `deadline_raw_text` | TEXT | Verbatim from source |
| `deadline_precision` | TEXT | CHECK in (`exact`, `day`, `month`, `unknown`) |
| `status` | TEXT | CHECK in (`upcoming`, `open`, `closed`, `undetermined`) |
| `status_confidence` | TEXT | CHECK in (`confirmed`, `ambiguous`, `unresolved`) |
| `is_current` | BOOL | The cycle the UI treats as the active one |
| `notes` | TEXT | |
| `created_at/updated_at` | TIMESTAMPTZ | |

Indexes: `(scholarship_id, intake_year)` UNIQUE; `deadline_at`; `status, is_current`.

### `eligibility_rules`
Typed, machine-checkable conditions scoped to a cycle.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `cycle_id` | UUID | FK→scholarship_cycles |
| `kind` | TEXT | CHECK in the rule-kind registry (`nationality`, `degree_level`, `gpa`, `age`, `work_experience`, `language`, `field_of_study`, `document_required`, `application_prerequisite`, `funding_requirement`, `course_requirement`, `discipline`, `other`) |
| `subject` | TEXT | What the rule constrains (e.g. `nationality`, `age.max_years`, `gpa.min_overall`) |
| `operator` | TEXT | CHECK in (`equals`, `not_equals`, `in`, `not_in`, `gte`, `lte`, `between`, `contains`, `required`, `absent`) |
| `value` | JSONB | The threshold/condition |
| `comparator` | TEXT | `mandatory` | `optional` | `preference` |
| `rule_text` | TEXT | Verbatim source wording (the human explanation anchor) |
| `evidence_ids` | JSONB | array of evidence_claims.id |
| `source_snapshot_id` | UUID | FK→source_snapshots |
| `confidence` | FLOAT | 0..1 extraction confidence |
| `ambiguity_flag` | BOOL | Wording unclear → verdict `needs_review` |
| `authored_by` | TEXT | `human` | `llm_proposed` | `llm_accepted` |
| `version` | INT | Rule-set version for assessment reproducibility |
| `created_at/updated_at` | TIMESTAMPTZ | |

Index: `(cycle_id)`.

### `funding_components`
Component-level coverage. Never a single "fully funded" boolean.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `cycle_id` | UUID | FK→scholarship_cycles |
| `component` | TEXT | CHECK in (`tuition`, `stipend`, `travel`, `accommodation`, `insurance`, `equipment`, `research`, `other`) |
| `coverage_status` | TEXT | CHECK in (`included`, `excluded`, `conditional`, `unknown`) |
| `amount` | NUMERIC(12,2) | NULL |
| `currency` | CHAR(3) | NULL |
| `amount_period` | TEXT | e.g. `per_year`, `one_off` |
| `conditions` | TEXT | Conditions attached to this component |
| `evidence_ids` | JSONB | |
| `source_snapshot_id` | UUID | |
| `created_at/updated_at` | TIMESTAMPTZ | |

Index: `(cycle_id)`.

### `required_documents`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `cycle_id` | UUID | FK |
| `doc_type` | TEXT | e.g. `passport`, `transcript`, `sop`, `lor`, `cv`, `research_proposal`, `proof_of_registration` |
| `is_mandatory` | BOOL | |
| `description` | TEXT | |
| `lead_time_days` | INT | Estimated preparation lead time (used by the planner) |
| `evidence_ids` | JSONB | |
| `created_at/updated_at` | TIMESTAMPTZ | |

---

## 3. Provenance & evidence

### `source_documents`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `scholarship_id` | UUID | FK→scholarships, NULL for general sources |
| `url` | TEXT | UNIQUE |
| `source_type` | TEXT | `funder_page`, `university_page`, `government_notice`, `application_portal`, `pdf`, `other` |
| `trust_tier` | TEXT | CHECK in (`official_primary`, `official_secondary`, `partner`, `aggregator`) |
| `country_iso3` | CHAR(3) | NULL |
| `refresh_cadence_hours` | INT | Default per source type (e.g. 24 for high-churn, 168 default) |
| `last_checked_at` | TIMESTAMPTZ | Last attempt |
| `last_success_at` | TIMESTAMPTZ | Last successful fetch |
| `fetch_status` | TEXT | CHECK in (`ok`, `error`, `blocked`, `not_found`) |
| `fetch_error` | TEXT | |
| `consecutive_failures` | INT | Drives backoff and `stale` marking |
| `is_enabled` | BOOL | Admin kill-switch |
| `robots_note` | TEXT | |
| `created_at/updated_at` | TIMESTAMPTZ | |

### `source_snapshots`
Immutable captures.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `source_document_id` | UUID | FK→source_documents |
| `content_hash` | TEXT | SHA-256 of normalized content; UNIQUE with source_document_id |
| `raw_content` | BYTEA | Original bytes (HTML/PDF) |
| `extracted_text` | TEXT | Cleaned text used for extraction and chunking |
| `http_status` | INT | |
| `headers` | JSONB | Selected response headers (ETag, Last-Modified, Content-Type) |
| `fetched_at` | TIMESTAMPTZ | |
| `extraction_version` | TEXT | |
| `fetched_by` | TEXT | `scheduler` | `manual` | `seed` |

### `evidence_chunks`
Retrieval unit.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `snapshot_id` | UUID | FK→source_snapshots |
| `source_document_id` | UUID | FK→source_documents |
| `section_path` | TEXT | e.g. `> Eligibility > Nationality` |
| `char_start` / `char_end` | INT | Offsets into `extracted_text` |
| `content` | TEXT | Chunk text |
| `content_hash` | TEXT | |
| `embedding` | vector(N) | pgvector; N and model recorded in `embedding_model` |
| `embedding_model` | TEXT | |
| `tsv` | TSVECTOR | Generated column: `to_tsvector('english', content)` |
| `token_count` | INT | |
| `created_at` | TIMESTAMPTZ | |

Indexes: GIN on `tsv`; IVFFlat/HNSW on `embedding`; `(source_document_id)`.

### `evidence_claims`
Atomic factual statements.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `snapshot_id` | UUID | FK→source_snapshots |
| `chunk_id` | UUID | FK→evidence_chunks |
| `span_start` / `span_end` | INT | Character span in snapshot text |
| `claim_text` | TEXT | |
| `claim_type` | TEXT | `deadline`, `funding`, `eligibility`, `document`, `contact`, `process`, `general` |
| `subject_entity` | TEXT | `scholarships` | `scholarship_cycles` | `source_documents` |
| `subject_id` | UUID | NULL |
| `field_name` | TEXT | NULL |
| `normalized_value` | JSONB | Typed normalized value |
| `validation_status` | TEXT | CHECK in (`confirmed`, `ambiguous`, `unresolved`, `conflicting`, `stale`, `rejected`) |
| `confidence` | FLOAT | |
| `extraction_method` | TEXT | `llm`, `rule`, `manual` |
| `reviewed_by` | UUID | FK→users, NULL |
| `reviewed_at` | TIMESTAMPTZ | |
| `created_at/updated_at` | TIMESTAMPTZ | |

### `change_events`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `source_document_id` | UUID | FK |
| `prev_snapshot_id` / `new_snapshot_id` | UUID | FK |
| `cycle_id` | UUID | FK, NULL if not cycle-scoped |
| `field_name` | TEXT | |
| `old_value` / `new_value` | JSONB | |
| `change_type` | TEXT | CHECK in (`deadline`, `opening_date`, `funding`, `eligibility`, `document`, `process`, `contact`, `cosmetic`) |
| `severity` | TEXT | CHECK in (`informational`, `important`, `critical`) |
| `detected_at` | TIMESTAMPTZ | |
| `review_status` | TEXT | CHECK in (`pending`, `approved`, `rejected`, `auto_accepted`) |
| `reviewed_by` | UUID | FK, NULL |
| `reviewed_at` | TIMESTAMPTZ | |
| `review_note` | TEXT | |
| `auto_accept_confidence` | FLOAT | Threshold used when auto-accepted |

### `conflicts`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `entity_type` / `entity_id` | TEXT / UUID | e.g. `scholarship_cycles` |
| `field_name` | TEXT | |
| `value_a` / `value_b` | JSONB | |
| `evidence_id_a` / `evidence_id_b` | UUID | FK→evidence_claims |
| `source_document_id_a` / `_b` | UUID | FK |
| `status` | TEXT | CHECK in (`open`, `resolved`, `dismissed`) |
| `resolution_note` | TEXT | |
| `created_at/updated_at` | TIMESTAMPTZ | |

---

## 4. Users, profiles, applications

### `users`
`id UUID PK`, `email CITEXT UNIQUE`, `password_hash TEXT`, `full_name TEXT`, `role TEXT`
(`student`|`admin`|`researcher`), `email_verified BOOL`, `country_iso3 CHAR(3)`, `is_active BOOL`,
`created_at/updated_at`.

### `student_profiles`
One row per user.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK→users UNIQUE |
| `nationality_country_iso3` | CHAR(3) | |
| `residency_country_iso3` | CHAR(3) | |
| `current_degree_level` | TEXT | degree_levels.code |
| `current_institution` | TEXT | |
| `degree_completion_year` | INT | |
| `fields_of_study` | JSONB | array |
| `gpa_value` / `gpa_scale` | NUMERIC / TEXT | |
| `age` | INT | |
| `work_experience_months` | INT | |
| `languages` | JSONB | [{code, level}] |
| `preferred_destinations` | JSONB | array of ISO3 |
| `preferred_study_modes` | JSONB | `onsite`/`remote`/`hybrid` |
| `funding_requirements` | JSONB | components the student considers essential |
| `target_intake_year` | INT | Default 2027 |
| `completeness` | FLOAT | 0..1 computed by service, used for "missing info" prompts |
| `created_at/updated_at` | TIMESTAMPTZ | |

### `saved_scholarships`
`id UUID PK`, `user_id FK`, `scholarship_id FK`, `note TEXT`, `priority INT`, `created_at` — UNIQUE(user_id, scholarship_id).

### `applications`
`id UUID PK`, `user_id FK`, `scholarship_id FK`, `cycle_id FK`, `status TEXT`
(`planning`|`preparing`|`submitted`|`accepted`|`rejected`|`withdrawn`|`closed`),
`target_deadline TIMESTAMPTZ`, `notes TEXT`, `created_at/updated_at` — UNIQUE(user_id, cycle_id).

### `application_tasks`
`id UUID PK`, `application_id FK`, `title TEXT`, `task_type TEXT`
(`document`|`form`|`request`|`submission`|`research`|`other`), `due_at TIMESTAMPTZ`,
`status TEXT` (`todo`|`in_progress`|`done`|`blocked`|`skipped`), `depends_on_task_id UUID FK` (self),
`doc_type TEXT`, `is_auto_generated BOOL`, `notes TEXT`, `completed_at TIMESTAMPTZ`,
`created_at/updated_at`.

### `alerts`
`id UUID PK`, `user_id FK`, `scholarship_id FK NULL`, `alert_type TEXT`
(`deadline`|`cycle_opening`|`source_change`|`task_due`), `channel TEXT` (`in_app`|`email`),
`is_enabled BOOL`, `created_at/updated_at`.

### `alert_deliveries`
`id UUID PK`, `alert_id FK`, `event_type TEXT`, `event_id UUID`, `delivered_at TIMESTAMPTZ`,
`status TEXT` (`sent`|`failed`|`skipped`), `error TEXT`.

---

## 5. Retrieval, generation, evaluation

### `answer_audits`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK, NULL for anonymous |
| `question` | TEXT | |
| `question_type` | TEXT | `fact`, `eligibility`, `conflict`, `prior_cycle`, `insufficient` |
| `retrieved_chunk_ids` | JSONB | Ordered list |
| `retrieval_config` | JSONB | {mode, top_k, rrf_k, rerank, filters} |
| `answer_claims` | JSONB | Structured output payload |
| `citation_map` | JSONB | claim index → evidence ids |
| `validation_result` | JSONB | {referential_ok, support_ok, reconciled, verdict} |
| `abstained` | BOOL | |
| `model_id` / `prompt_version` | TEXT | |
| `embedding_model` | TEXT | |
| `latency_ms` | INT | |
| `cost_usd` | NUMERIC(10,6) | |
| `created_at` | TIMESTAMPTZ | |

### `eligibility_assessments`
`id UUID PK`, `user_id FK`, `cycle_id FK`, `engine_version TEXT`, `ruleset_version INT`,
`profile_hash TEXT` (hash of the profile facts used), `overall_status TEXT`
(`eligible`|`likely_eligible`|`unknown`|`not_eligible`|`needs_review`),
`verdict_counts JSONB`, `results JSONB` (per-rule verdict, reason, evidence ids),
`created_at` — UNIQUE(user_id, cycle_id, engine_version, ruleset_version, profile_hash).

### `ingestion_jobs`
`id UUID PK`, `source_document_id FK`, `task_id TEXT`, `status TEXT`
(`queued`|`running`|`succeeded`|`failed`|`dead`), `attempts INT`, `last_error TEXT`,
`started_at`, `finished_at`, `created_at`.

### `evaluation_runs`
`id UUID PK`, `experiment_id TEXT`, `dataset_version TEXT`, `split TEXT`, `config JSONB`,
`metrics JSONB`, `model_id TEXT`, `code_commit TEXT`, `started_at`, `finished_at`.

### `evaluation_items`
Gold dataset (also versioned in `data/fixtures/eval/*.jsonl`).
`id TEXT PK`, `question TEXT`, `question_type TEXT`, `split TEXT` (`dev`|`heldout`),
`required_evidence JSONB` (list of {claim, source_hint}), `gold_answer TEXT`,
`acceptable_abstain BOOL`, `eligibility_case TEXT` (for Exp B),
`scholarship_slug TEXT NULL`, `notes TEXT`.

---

## 6. Relationship summary

```
source_documents 1─n source_snapshots 1─n evidence_chunks 1─n evidence_claims
       │                    │                                    │
       │                    └────────────── change_events ◄─────┘
       │                                     │
scholarships 1─n scholarship_cycles 1─n eligibility_rules
       │                │            1─n funding_components
       │                │            1─n required_documents
       │                │
       │                └── n applications (user-scoped) 1─n application_tasks
       │                                        └── n alerts 1─n alert_deliveries
       └── n saved_scholarships (user-scoped)

users 1─1 student_profiles 1─n eligibility_assessments
users 1─n answer_audits
```

---

## 7. Data-quality rules (enforced in services + CI checks)

1. Every `scholarships` row has a non-null `canonical_source_id` with `trust_tier` in official tiers.
2. Every `scholarship_cycles` row has `intake_year` and a status; `deadline_at` NULL allowed only when `deadline_raw_text` exists and `deadline_precision != 'unknown'` is false → status `undetermined`.
3. Every `eligibility_rules` row has `rule_text` and at least one `evidence_id` unless `authored_by='human'` with a documented manual source note.
4. Every `funding_components` row has a `coverage_status` in the 4-value set; `amount` requires `currency`.
5. Every `evidence_claims` row has a `snapshot_id` and a non-empty `span_start < span_end`.
6. `change_events` with `severity='critical'` must have `review_status != 'pending'` before the affected fact may be `confirmed`.
7. `student_profiles.gpa_value` requires `gpa_scale`.
8. `answer_audits.citation_map` must only reference chunk ids present in the same row's `retrieved_chunk_ids`.
9. Deleted users → cascade personal data; `answer_audits` retain only de-identified questions.

## 8. Retention & privacy
- `source_snapshots.raw_content`: retained indefinitely (public information, supports re-extraction).
- Profile PII: retained while the account is active; hard-delete on account deletion (cascade).
- `answer_audits`: 24 months rolling, de-identified on export.
- Document uploads (future): 90 days default, user-deletable.
