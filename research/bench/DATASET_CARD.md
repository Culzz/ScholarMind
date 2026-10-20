# ScholarBench-Africa — dataset card

**Name:** ScholarBench-Africa
**Version:** `bench-v1.0` (release line `bench-v1`)
**Created:** 2026-10-20
**Creator:** ScholarMind research track — dataset authored by the project owner
(`ann_primary`). A second annotator has not yet been assigned.
**Licence:** questions and evidence descriptions **CC BY 4.0**; gold labels and
verdicts **CC0 1.0**; tooling under `research/bench/tools/` **MIT**. All content
is provided as is, without warranty of any kind.
**Protocol reference:** `docs/EVALUATION.md` §11 (benchmark), §12 (adversarial
suite), §15 (LLM-judge validation), §16 (cost and latency).

---

## 1. Purpose

ScholarBench-Africa is the public, versioned release of the ScholarMind gold
set. It exists so that the numbers reported for scholarship search, eligibility
reasoning, abstention and freshness can be checked by someone who does not have
access to the private corpus.

It is a **benchmark artefact, not a product export**. It contains no user data,
no captured page bodies and no snapshot mirrors.

## 2. Contents

| File | Records | What it measures |
|---|---|---|
| `bench-v1/questions.jsonl` | 36 | Question answering over scholarship facts, eligibility, conflicts, prior cycles, abstention and injected sources |
| `bench-v1/eligibility_pairs.jsonl` | 24 | (profile, scholarship) pairs with per-rule gold verdicts |
| `bench-v1/change_pairs.jsonl` | 20 | Before/after snapshot edits, including 6 untouched controls |
| `bench-v1/adversarial.jsonl` | 18 | Prompt-injection, expired-cycle, near-duplicate, conflicting-deadline, funding-conditional, fully-funded-trap and empty-source cases |
| `bench-v1/manifest.json` | — | Version, counts, distributions, annotation status, licence and SHA-256 of every data file |

Total: 98 records.

## 3. Question classes, minimum counts and the metrics each class feeds

Minimums are the class minimums recorded in `docs/EVALUATION.md` §11.6 for
`bench-v1`. **Every class in this release is below its minimum** — `bench-v1` is
a scaffold release. The shortfall is recorded in `CHANGELOG.md` and repeated in
`manifest.json` (`class_shortfall`) so that it is never silent.

| # | `question_type` | Min (§11.6) | In `bench-v1.0` | Primary metrics | Also informs |
|---|---|---|---|---|---|
| 1 | `fact` | 40 | 6 | Answer correctness, citation precision, Recall@5/10 | Hallucinated-fact rate, MRR |
| 2 | `eligibility` | 40 | 6 | Rule-level precision/recall/F1, false-positive eligibility rate | Correct-unknown rate, needs-review recall, overall accuracy |
| 3 | `conflict` | 20 | 6 | Conflict surfacing rate, wrong-answer rate | Citation completeness, trust-tier behaviour |
| 4 | `prior_cycle` | 20 | 6 | Expired-cycle answer rate, wrong-answer rate | Abstain precision on stale data |
| 5 | `insufficient` | 40 | 6 | Correct-abstain rate, wrong-answer rate (headline) | Abstention calibration, ECE on abstention |
| 6 | `adversarial` | 20 | 6 | Injection-isolation rate (must be 1.00), injection detection | Adversarial suite pass rate, abstention on empty sources |

Splits in `bench-v1.0`: 24 `dev`, 12 `heldout` (4 dev / 2 held-out per class).
The held-out split is run once per release and never feeds a threshold
(`docs/EVALUATION.md` §18.4).

## 4. Source policy

* **No full page text is redistributed.** The release contains questions, evidence
  *descriptions* (a one-line statement of what a snapshot must show), snapshot id
  placeholders and content hashes. It contains no page body, no paragraph copy
  and no snapshot mirror.
* **Snapshots are referenced by id, never mirrored.** A snapshot id resolves to an
  internal archive record.
* **Funder pages remain the property of their owners.** The release links to the
  canonical source and publishes facts, not copies.
* **Redaction is enforced mechanically.** `tools/redact.py` fails the release if
  it finds a field over 2000 characters, an evidence marker or a contiguous run
  of 300 or more characters (the shape of a copied paragraph), a content-bearing
  key (`raw_content`, `extracted_text`, `content`, `page_text`) outside the
  allowlist, a URL outside the allowlisted official domains, or an e-mail address
  outside a reserved example domain. `tools/publish.py` runs the same check and
  refuses to write an artifact if it trips.
* **No user data.** Every profile in the eligibility pairs is synthetic.

## 5. Annotation protocol

1. **Drafting.** The author writes the question, the required evidence, the gold
   answer and the notes naming the exact field to check on the official page.
2. **Independent labelling.** Two annotators label independently: per-rule
   eligibility verdicts, `overall_status`, conflict resolution, and whether the
   evidence supports the answer.
3. **Adjudication.** Disagreements are adjudicated by a third reviewer (or by the
   author when no third reviewer exists — recorded in the manifest). The
   adjudicated label is the gold label.
4. **Agreement.** Cohen's κ is reported per class. For the eligibility and
   conflict classes, κ < 0.6 blocks further labelling until the annotation
   guidelines are revised.
5. **Invalidation.** An item whose required evidence later changes is marked
   stale and moved to the next version with the reason recorded in the changelog.
6. **Adversarial items** are validated against at least two independent
   implementations before they gate a release.

**Current status in `bench-v1.0`:** one annotator (`ann_primary`), no second
annotator, no adjudication, **κ not measurable**. `manifest.json` records this
under `annotation_status` and the card is not to be cited as an
agreement-validated dataset. A second labelling pass is required before
`bench-v1.1`.

## 6. Verification status — read this before citing any number

**No item in `bench-v1.0` is verified.** The source corpus has not been captured
yet, so no item can be checked against a live snapshot. Accordingly:

* every record carries `"verified": false`;
* every `gold_answer` is a **specification of the answer**, not a captured value
  (for example: *"the 2027 cycle deadline as stated on the funder's official
  page, in ISO format, with the page's own wording preserved"*);
* every `notes` field names the exact field to check on the official page and
  states that the template is pending snapshot verification.

`bench-v1.0` may be used to exercise harnesses, to test the tooling and to
develop annotations. It may **not** be used to report accuracy numbers: a
template gold answer cannot score a system.

## 7. Known limitations

1. **Single author.** The gold set is written by the same person building the
   system. Mitigation: the annotation protocol requires a second annotator and
   published κ, and the gap is stated here rather than smoothed over.
2. **Nigeria-first, small corpus.** Items are drawn from the `nigeria_v1`
   manifest (28 sources, mostly Nigerian and South African). Conclusions do not
   transfer to other regions, funders or a larger catalogue.
3. **Small sample.** 36 questions, 24 pairs, 20 change pairs, 18 adversarial
   items. Confidence intervals on any metric computed from them are wide; the
   release gate thresholds in `docs/EVALUATION.md` §18 are *not* met by a
   dataset of this size and must not be claimed as met.
4. **Synthetic edits.** The change set is produced by editing real-shaped
   snapshots; the edits are synthetic, not archival. Real archived pairs are
   added as the archive fills.
5. **Unverified labels.** See §6.
6. **Judge dependence.** Answer correctness relies on an LLM judge plus human
   sampling (`docs/EVALUATION.md` §15). Until the judge is calibrated against
   humans (κ ≥ 0.7, per-class F1 ≥ 0.75), the dependent metric families are
   human-scored only.
7. **Cadence-bound freshness claims.** Detection latency is a distribution over a
   refresh cadence, not a guarantee.

## 8. Intended use

* Benchmarking retrieval, answering, eligibility reasoning, conflict handling,
  abstention and change detection over African scholarship sources.
* Regression testing of the ScholarMind pipeline against a fixed, versioned set.
* Reproducing the numbers in `docs/EVALUATION.md` from a clean checkout.

### Out of scope

* Training or fine-tuning on the gold answers.
* Product use, ranking in a user-facing surface, or any decision affecting a
  real applicant.
* Claiming eligibility advice: the benchmark measures a system, it does not
  confer eligibility on any person.

## 9. File schemas

All files are JSONL: one compact JSON object per line, UTF-8, LF endings, no
trailing commas.

### 9.1 `bench-v1/questions.jsonl`

| Field | Type | Notes |
|---|---|---|
| `id` | string | `q_b1_<class>_<nnn>`, unique within the release |
| `question` | string | Natural-language question |
| `question_type` | string | one of `fact`, `eligibility`, `conflict`, `prior_cycle`, `insufficient`, `adversarial` |
| `split` | string | `dev` or `heldout` |
| `difficulty` | integer | 1–5 |
| `scholarship_slug` | string | slug of the scholarship the item refers to (may be a closed-cycle slug) |
| `required_evidence` | array of object | each `{claim, source_hint, snapshot_hint}`; `snapshot_hint` is `pending-capture` or `pending-archive` until the corpus is captured |
| `gold_answer` | string | the specification of the correct answer (see §6) |
| `acceptable_abstain` | boolean | `true` counts as correct only on a proper abstention that names what is missing |
| `verified` | boolean | always `false` in `bench-v1.0` |
| `notes` | string | names the exact field to check on the official page |

### 9.2 `bench-v1/eligibility_pairs.jsonl`

| Field | Type | Notes |
|---|---|---|
| `id` | string | `ep_b1_elig_<nnn>` |
| `scholarship_slug` | string | |
| `cycle_label` | string | e.g. `2027-cycle`, `2026-cycle` |
| `profile` | object | `nationality`, `degree_level`, `age`, `field_of_study`, `work_experience_months`, `ielts`, `degrees`, **and** either `gpa_value` + `gpa_scale` **or** `grade_scale_raw` (never both; a missing-profile case may omit both) |
| `gold_overall_status` | string | `eligible`, `likely_eligible`, `unknown`, `not_eligible`, `needs_review` |
| `gold_rule_verdicts` | array of object | each `{kind, subject, verdict, reason}`; `verdict` ∈ `satisfied`, `not_satisfied`, `unknown`, `needs_review` |
| `edge_case` | string | `clearly_eligible`, `one_mandatory_failure`, `missing_profile_data`, `ambiguous_wording`, `conflicting_requirements`, `cycle_specific` (4 of each in `bench-v1.0`) |
| `verified` | boolean | always `false` |
| `notes` | string | |

**Grade-scale rule.** Where a verdict depends on converting between scales
(Second Class Upper ↔ CGPA 5.0 ↔ percentage ↔ GPA 4.0), the verdict is
`needs_review`, never `satisfied`, unless the source page itself states the
equivalence. This is the platform's documented conservative behaviour
(`scholarmind/normalization/grades.py`).

### 9.3 `bench-v1/change_pairs.jsonl`

| Field | Type | Notes |
|---|---|---|
| `id` | string | `cp_b1_chg_<nnn>` |
| `source_document_id` | string | placeholder snapshot id (`sd_placeholder_00nn`) until capture |
| `field_name` | string | typed field, e.g. `application_deadline`, `funding_package`, `eligibility_rule.age` |
| `old_value` | string | value before the edit |
| `new_value` | string | value after the edit |
| `change_type` | string | `deadline`, `opening_date`, `funding`, `eligibility`, `document`, `process`, `contact`, `cosmetic` |
| `expected_severity` | string | `critical`, `high`, `medium`, `low`, `none` |
| `is_control` | boolean | `true` for untouched pairs (`old_value == new_value`); 6 of 20 in `bench-v1.0`, used to measure the false-alarm rate |
| `verified` | boolean | always `false` |
| `notes` | string | |

### 9.4 `bench-v1/adversarial.jsonl`

| Field | Type | Notes |
|---|---|---|
| `id` | string | `adv_b1_<nnn>` |
| `family` | string | `injection_page`, `expired_cycle`, `near_duplicate`, `conflicting_deadline`, `funding_conditional`, `fully_funded_trap`, `empty_source` |
| `input` | string | the page text, the question, or the conflicting pair, prefixed by its kind (`page_text:`, `question:`, `conflicting_pair:`) |
| `expected_behaviour` | string | the precise behaviour the system must show |
| `automated_check` | string | the name of the check that enforces it, e.g. `assert_injection_sentinel_absent` |
| `blocks_release` | boolean | `true` for `injection_page`, `expired_cycle` and `fully_funded_trap` |
| `verified` | boolean | always `false` |
| `notes` | string | |

## 10. How to cite

> ScholarMind research track. *ScholarBench-Africa*, version `bench-v1.0`
> (release line `bench-v1`), created 2026-10-20. Nigeria-first scholarship
> benchmark: 36 questions across 6 classes, 24 eligibility pairs, 20 change
> pairs, 18 adversarial items. Questions licensed CC BY 4.0; gold labels
> licensed CC0 1.0. Artefact version `bench-v1.0`.

BibTeX:

```bibtex
@misc{scholarmind_scholarbench_africa_v1_0,
  title        = {ScholarBench-Africa},
  version      = {bench-v1.0},
  year         = {2026},
  month        = {10},
  note         = {Questions: CC BY 4.0. Gold labels: CC0 1.0. Tooling: MIT.},
  howpublished = {ScholarMind research track}
}
```

Results that use this benchmark must record `dataset_version: bench-v1.0` in
their results file (`docs/EVALUATION.md` §6). Results across versions are not
comparable without a re-run on the newer version.
