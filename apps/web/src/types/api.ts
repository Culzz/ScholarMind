/**
 * Typed contracts for the ScholarMind REST API (v1).
 *
 * These mirror `docs/DATA_DICTIONARY.md` and `docs/SRS.md`. Field names are
 * `snake_case` on the wire so the payload can be passed through untouched.
 */

/* ------------------------------------------------------------------ *
 * Vocabularies
 * ------------------------------------------------------------------ */

/**
 * User-facing claim states (SRS §2, PLAN §11).
 *
 * These are deliberately *not* the same set as the persisted
 * `evidence_claims.validation_status`; see `lib/claims.ts` for the mapping.
 */
export type ClaimState =
  | 'confirmed'
  | 'not_established'
  | 'needs_verification'
  | 'stale'
  | 'expired';

/** Persisted validation status of an evidence claim. */
export type EvidenceValidationStatus =
  | 'confirmed'
  | 'ambiguous'
  | 'unresolved'
  | 'conflicting'
  | 'stale'
  | 'rejected';

/** Per-rule eligibility verdict (FR-3.2). */
export type Verdict = 'satisfied' | 'not_satisfied' | 'unknown' | 'needs_review';

/** Aggregate status for a (profile, cycle) assessment. */
export type OverallStatus =
  | 'eligible'
  | 'likely_eligible'
  | 'unknown'
  | 'not_eligible'
  | 'needs_review';

/** Source trust tier. */
export type TrustTier = 'official_primary' | 'official_secondary' | 'partner' | 'aggregator';

export type SourceType =
  | 'funder_page'
  | 'university_page'
  | 'government_notice'
  | 'application_portal'
  | 'pdf'
  | 'other';

export type FetchStatus = 'ok' | 'error' | 'blocked' | 'not_found';

export type ProviderType =
  | 'government'
  | 'university'
  | 'foundation'
  | 'ngo'
  | 'corporate'
  | 'multilateral'
  | 'other';

export type DegreeLevel =
  | 'bachelors'
  | 'masters'
  | 'mba'
  | 'phd'
  | 'postdoc'
  | 'research';

export type CycleStatus = 'upcoming' | 'open' | 'closed' | 'undetermined';

export type CycleStatusConfidence = 'confirmed' | 'ambiguous' | 'unresolved';

export type DatePrecision = 'exact' | 'day' | 'month' | 'year' | 'unknown';

export type RuleKind =
  | 'nationality'
  | 'residency'
  | 'degree_level'
  | 'gpa'
  | 'age'
  | 'work_experience'
  | 'language'
  | 'field_of_study'
  | 'document_required'
  | 'application_prerequisite'
  | 'funding_requirement'
  | 'course_requirement'
  | 'discipline'
  | 'other';

export type RuleComparability = 'mandatory' | 'optional' | 'preference';

export type RuleOperator =
  | 'equals'
  | 'not_equals'
  | 'in'
  | 'not_in'
  | 'gte'
  | 'lte'
  | 'between'
  | 'contains'
  | 'required'
  | 'absent';

/** Coverage of one funding component. Never a single "fully funded" boolean. */
export type CoverageStatus = 'included' | 'excluded' | 'conditional' | 'unknown';

export type FundingComponentKind =
  | 'tuition'
  | 'stipend'
  | 'travel'
  | 'accommodation'
  | 'insurance'
  | 'equipment'
  | 'research'
  | 'other';

export type FundingAmountPeriod = 'per_year' | 'per_month' | 'one_off' | 'unknown';

export type ChangeType =
  | 'deadline'
  | 'opening_date'
  | 'funding'
  | 'eligibility'
  | 'document'
  | 'process'
  | 'contact'
  | 'cosmetic';

export type ChangeSeverity = 'informational' | 'important' | 'critical';

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'auto_accepted';

export type ApplicationStatus =
  | 'planning'
  | 'preparing'
  | 'submitted'
  | 'accepted'
  | 'rejected'
  | 'withdrawn'
  | 'closed';

export type TaskType = 'document' | 'form' | 'request' | 'submission' | 'research' | 'other';

export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked' | 'skipped';

export type ClaimType =
  | 'deadline'
  | 'funding'
  | 'eligibility'
  | 'document'
  | 'contact'
  | 'process'
  | 'general';

/* ------------------------------------------------------------------ *
 * Core entities
 * ------------------------------------------------------------------ */

export interface Destination {
  country_iso3: string;
  institution?: string | null;
  note?: string | null;
}

export interface SourceDocument {
  id: string;
  scholarship_id: string | null;
  url: string;
  source_type: SourceType;
  trust_tier: TrustTier;
  country_iso3: string | null;
  refresh_cadence_hours: number;
  last_checked_at: string | null;
  last_success_at: string | null;
  fetch_status: FetchStatus;
  fetch_error: string | null;
  consecutive_failures: number;
  is_enabled: boolean;
  robots_note?: string | null;
  /** UI-facing state derived from fetch status / age. */
  claim_state: ClaimState;
}

export interface Scholarship {
  id: string;
  slug: string;
  name: string;
  provider_type: ProviderType;
  provider_name: string;
  provider_country_iso3: string | null;
  description: string | null;
  study_levels: DegreeLevel[];
  fields_of_study: string[];
  destinations: Destination[];
  canonical_source_id: string | null;
  trust_tier: TrustTier;
  website_url: string | null;
  status: 'active' | 'inactive' | 'archived';
  created_at?: string;
  updated_at?: string;
}

export interface ScholarshipCycle {
  id: string;
  scholarship_id: string;
  intake_year: number;
  cycle_label: string;
  opens_at: string | null;
  opens_at_precision: DatePrecision;
  deadline_at: string | null;
  deadline_timezone: string | null;
  deadline_raw_text: string | null;
  deadline_precision: DatePrecision;
  status: CycleStatus;
  status_confidence: CycleStatusConfidence;
  is_current: boolean;
  notes: string | null;
  /** UI-facing claim state for the deadline / cycle status. */
  claim_state: ClaimState;
  rule_count?: number;
  funding_component_count?: number;
}

export interface EligibilityRule {
  id: string;
  cycle_id: string;
  kind: RuleKind;
  subject: string;
  operator: RuleOperator;
  value: unknown;
  comparability: RuleComparability;
  rule_text: string;
  evidence_ids: string[];
  source_snapshot_id: string | null;
  confidence: number;
  ambiguity_flag: boolean;
  authored_by: 'human' | 'llm_proposed' | 'llm_accepted';
  version: number;
}

export interface FundingComponent {
  id: string;
  cycle_id: string;
  component: FundingComponentKind;
  coverage_status: CoverageStatus;
  amount: number | null;
  currency: string | null;
  amount_period: FundingAmountPeriod;
  conditions: string | null;
  evidence_ids: string[];
  source_snapshot_id: string | null;
  /** UI-facing claim state for the coverage fact. */
  claim_state: ClaimState;
}

export interface EvidenceClaim {
  id: string;
  snapshot_id: string;
  chunk_id: string | null;
  span_start: number;
  span_end: number;
  claim_text: string;
  claim_type: ClaimType;
  subject_entity: 'scholarships' | 'scholarship_cycles' | 'source_documents';
  subject_id: string | null;
  field_name: string | null;
  normalized_value: unknown;
  validation_status: EvidenceValidationStatus;
  confidence: number;
  extraction_method: 'llm' | 'rule' | 'manual';
  /** Verbatim excerpt from the snapshot the claim was extracted from. */
  excerpt?: string | null;
  source_url?: string | null;
  source_name?: string | null;
  snapshot_at?: string | null;
  trust_tier?: TrustTier | null;
}

export interface ChangeEvent {
  id: string;
  source_document_id: string;
  prev_snapshot_id: string | null;
  new_snapshot_id: string | null;
  cycle_id: string | null;
  field_name: string;
  old_value: unknown;
  new_value: unknown;
  change_type: ChangeType;
  severity: ChangeSeverity;
  detected_at: string;
  review_status: ReviewStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  source_name?: string | null;
  source_url?: string | null;
}

export interface Conflict {
  id: string;
  entity_type: string;
  entity_id: string | null;
  field_name: string;
  value_a: unknown;
  value_b: unknown;
  evidence_id_a: string | null;
  evidence_id_b: string | null;
  source_document_id_a: string | null;
  source_document_id_b: string | null;
  source_name_a?: string | null;
  source_name_b?: string | null;
  source_url_a?: string | null;
  source_url_b?: string | null;
  snapshot_at_a?: string | null;
  snapshot_at_b?: string | null;
  status: 'open' | 'resolved' | 'dismissed';
  resolution_note: string | null;
}

/* ------------------------------------------------------------------ *
 * Profile, assessments
 * ------------------------------------------------------------------ */

export interface ProfileLanguage {
  code: string;
  level: string;
}

export interface Profile {
  id: string;
  user_id?: string;
  nationality_country_iso3: string | null;
  residency_country_iso3: string | null;
  current_degree_level: DegreeLevel | null;
  current_institution: string | null;
  degree_completion_year: number | null;
  fields_of_study: string[];
  gpa_value: number | null;
  gpa_scale: string | null;
  age: number | null;
  work_experience_months: number | null;
  languages: ProfileLanguage[];
  preferred_destinations: string[];
  preferred_study_modes: string[];
  funding_requirements: FundingComponentKind[];
  target_intake_year: number;
  /** 0..1 — used for "what's still missing" prompts, never as an eligibility score. */
  completeness: number;
  updated_at?: string;
}

export interface ProfileInput {
  nationality_country_iso3?: string | null;
  residency_country_iso3?: string | null;
  current_degree_level?: DegreeLevel | null;
  current_institution?: string | null;
  degree_completion_year?: number | null;
  fields_of_study?: string[];
  gpa_value?: number | null;
  gpa_scale?: string | null;
  age?: number | null;
  work_experience_months?: number | null;
  languages?: ProfileLanguage[];
  preferred_destinations?: string[];
  preferred_study_modes?: string[];
  funding_requirements?: FundingComponentKind[];
  target_intake_year?: number;
}

export interface AssessmentResult {
  rule_id: string;
  kind: RuleKind;
  subject: string;
  comparability: RuleComparability;
  rule_text: string;
  verdict: Verdict;
  reason: string;
  profile_fact: unknown;
  missing_field: string | null;
  evidence_ids: string[];
}

export interface Assessment {
  id: string;
  cycle_id: string;
  scholarship_id?: string | null;
  scholarship_name?: string | null;
  cycle_label?: string | null;
  engine_version: string;
  ruleset_version: number;
  profile_hash: string;
  overall_status: OverallStatus;
  verdict_counts: Partial<Record<Verdict, number>>;
  missing_fields: string[];
  results: AssessmentResult[];
  created_at: string;
}

export interface EvaluateRequest {
  profile?: ProfileInput;
  cycle_ids?: string[];
  scholarship_ids?: string[];
}

export interface EvaluateResponse {
  assessments: Assessment[];
  engine_version: string;
  created_at?: string;
}

/* ------------------------------------------------------------------ *
 * Assistant
 * ------------------------------------------------------------------ */

export interface AssistantClaim {
  text: string;
  evidence_ids: string[];
  confidence: 'confirmed' | 'uncertain';
  /** UI-facing state; the API may omit it, in which case it is derived. */
  claim_state?: ClaimState;
}

export interface FreshnessWarning {
  source_id?: string | null;
  source_name?: string | null;
  message: string;
  claim_state: ClaimState;
  last_checked_at?: string | null;
}

export interface ValidationResult {
  referential_ok: boolean;
  support_ok: boolean;
  reconciled: boolean;
  verdict: 'ok' | 'downgraded' | 'abstained' | 'unverified';
}

export interface AssistantAnswer {
  id: string | null;
  question: string;
  answer: string;
  claims: AssistantClaim[];
  evidence: EvidenceClaim[];
  conflicts: Conflict[];
  freshness_warnings: FreshnessWarning[];
  abstained: boolean;
  abstention_reason: string | null;
  /** Facts the user must supply (or officials must publish) before an answer is possible. */
  missing_information: string[];
  follow_up_questions: string[];
  validation_result?: ValidationResult | null;
  created_at: string;
}

export interface AskRequest {
  question: string;
  scholarship_id?: string;
  cycle_id?: string;
}

/* ------------------------------------------------------------------ *
 * Discovery, comparison, recommendations
 * ------------------------------------------------------------------ */

export interface ScholarshipListItem extends Scholarship {
  current_cycle: ScholarshipCycle | null;
  next_deadline_at?: string | null;
  deadline_claim_state?: ClaimState;
  source_last_checked_at?: string | null;
  source_trust_tier?: TrustTier | null;
  official_url?: string | null;
  rule_count?: number;
}

export interface Paginated<T> {
  items: T[];
  next_cursor: string | null;
  total?: number | null;
}

export interface ScholarshipFilters {
  q?: string;
  nationality?: string;
  level?: string;
  field?: string;
  destination?: string;
  funding_component?: string;
  cycle_year?: number;
  verification?: ClaimState | '';
  deadline_window?: string;
  sort?: 'deadline' | 'relevance' | 'funding' | 'verification';
  cursor?: string | null;
  limit?: number;
}

export interface ScholarshipDetail {
  scholarship: Scholarship;
  cycles: ScholarshipCycle[];
  funding_components: FundingComponent[];
  sources: SourceDocument[];
  rules: EligibilityRule[];
  latest_assessment: Assessment | null;
}

export interface ChangeHistoryResponse {
  changes: ChangeEvent[];
  conflicts: Conflict[];
}

export interface CompareRequest {
  scholarship_ids: string[];
}

export interface SourceFreshness {
  source_id: string;
  source_name: string | null;
  trust_tier: TrustTier | null;
  last_checked_at: string | null;
  claim_state: ClaimState;
}

export interface ComparisonCell {
  /** Row key in the matrix, e.g. 'deadline' or 'funding.tuition'. */
  field: string;
  value: unknown;
  state: 'included' | 'excluded' | 'conditional' | 'unknown' | 'unresolved' | string;
  source: string | null;
  checked_at: string | null;
  note: string | null;
}

export interface ComparisonColumn {
  scholarship_id: string;
  name: string;
  cycle_id: string | null;
  deadline: string | null;
  deadline_state: 'confirmed' | 'unresolved' | string;
  source_url: string | null;
  source_checked_at: string | null;
  cells: Record<string, ComparisonCell>;
}

/**
 * The comparison engine's output: a matrix of per-field cells, one column per
 * scholarship. Every cell states the source it came from and never fills a gap
 * with a guess.
 */
export interface CompareResponse {
  fields: string[];
  columns: ComparisonColumn[];
  conflicts: Array<{
    id?: string;
    field_name?: string;
    value_a?: unknown;
    value_b?: unknown;
  }>;
  notes: string[];
}

export interface RecommendationFactor {
  key: string;
  label: string;
  /** Raw factor value, e.g. 0.75 for a confirmed-eligibility ratio. */
  value: number;
  weight: number;
  contribution: number;
  detail: string | null;
}

export interface Recommendation {
  scholarship_id: string;
  scholarship: Scholarship;
  cycle: ScholarshipCycle | null;
  /** A prioritisation aid. Never a probability of admission or success. */
  score: number;
  rank: number;
  factors: RecommendationFactor[];
  notes: string[];
}

export interface RecommendationResponse {
  items: Recommendation[];
  weights: Record<string, number>;
  weights_version: string;
  generated_at?: string;
}

/* ------------------------------------------------------------------ *
 * Planner
 * ------------------------------------------------------------------ */

export interface Application {
  id: string;
  scholarship_id: string;
  scholarship_name?: string | null;
  cycle_id: string;
  cycle_label?: string | null;
  status: ApplicationStatus;
  target_deadline: string | null;
  notes: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ApplicationTask {
  id: string;
  application_id: string;
  title: string;
  task_type: TaskType;
  due_at: string | null;
  status: TaskStatus;
  depends_on_task_id: string | null;
  doc_type: string | null;
  is_auto_generated: boolean;
  notes: string | null;
  completed_at: string | null;
  created_at?: string;
}

export interface CreateApplicationRequest {
  scholarship_id: string;
  cycle_id: string;
  notes?: string;
}

export interface UpdateTaskRequest {
  status?: TaskStatus;
  title?: string;
  due_at?: string | null;
  notes?: string | null;
}

/* ------------------------------------------------------------------ *
 * Auth
 * ------------------------------------------------------------------ */

export type UserRole = 'student' | 'admin' | 'researcher';

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  email_verified: boolean;
  country_iso3: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string;
}
