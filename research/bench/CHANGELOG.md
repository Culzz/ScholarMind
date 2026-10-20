# ScholarBench-Africa — changelog

All notable changes to the benchmark are recorded here. The format follows
`Keep a Changelog`; the dataset uses semantic versioning on top of the
`bench-vN` release line (`docs/EVALUATION.md` §11.3).

---

## Version history

| Version | Date | Release line | Change | Reason | Items added / removed / amended | Effect on headline metrics |
|---|---|---|---|---|---|---|
| `bench-v1.0` | 2026-10-20 | `bench-v1` | Initial scaffold release: 36 questions, 24 eligibility pairs, 20 change pairs, 18 adversarial items, manifest and tooling | Establish a versioned, citable benchmark surface before the source corpus is captured | Added 98 items; none removed; none amended | **None yet.** No metric is reported on this release: every item is `verified: false` and every gold answer is a template |

### `bench-v1.0` — recorded shortfalls

`docs/EVALUATION.md` §11.6 sets class minimums for `bench-v1`. This release is
below every one of them. The shortfall is recorded here and in
`bench-v1/manifest.json` (`class_shortfall`) so that it is never silent.

| Class | Minimum | In `bench-v1.0` | Shortfall | Reason |
|---|---|---|---|---|
| `fact` | 40 | 6 | −34 | Scaffold release: the `nigeria_v1` corpus has not been captured, so no item can be written against a verified snapshot |
| `eligibility` | 40 | 6 | −34 | As above |
| `conflict` | 20 | 6 | −14 | As above; conflict items additionally require two captured pages per item |
| `prior_cycle` | 20 | 6 | −14 | As above; prior-cycle items require the archive to contain the earlier cycle |
| `insufficient` | 40 | 6 | −34 | As above |
| `adversarial` | 20 | 6 | −14 | As above; adversarial items are written against synthetic snapshots by design |
| Eligibility pairs | 120 (§9, R3) | 24 | −96 | As above |
| Change pairs | 60 (§2.3) | 20 | −40 | As above; the replay set needs archived snapshot pairs |
| Adversarial suite | 18 (§12) | 18 | 0 | Item count is met; the items are unverified and are not yet wired into the CI gate |

The remaining gap is closed by the capture programme, not by writing more
unverified items.

---

## Versioning policy

### Version string

A version is `bench-v<line>.<minor>`, for example `bench-v1.0`.

* **line** (`bench-vN`) is the release line. A new line is cut when the corpus
  or the task definition changes in a way that invalidates comparison with
  earlier results.
* **minor** is the revision within the line.

The version string appears in every results file (`dataset_version`) and in
every published artifact name (`dist/bench-v<line>-<version>.jsonl`). A result
that does not carry it is invalid (`docs/EVALUATION.md` §6).

### What bumps which

| Change | Bump | Requirement |
|---|---|---|
| Items added (questions, pairs, adversarial items) | **minor** | Changelog entry naming the added ids |
| A breaking change to any item — question wording, `required_evidence`, `difficulty`, `split`, `edge_case`, `notes`, `expected_sehaviour`, `automated_check` | **minor** | Changelog entry naming the amended ids and the reason |
| A redaction rule change that alters the published content | **minor** | Changelog entry; re-run the redaction check over the whole release |
| An item removed | **major** | Changelog entry, re-baseline commit, re-run of the benchmark |
| The **gold answer** of an item changed (`gold_answer`, `gold_overall_status`, a `gold_rule_verdicts` entry, a `gold_overall_status` value) | **major** | Changelog entry naming the item and the old and new label, **re-baseline commit**, re-run of the benchmark |
| An item invalidated because its required evidence changed | **major** | Item moved to the next version as stale, with the reason recorded |

### The re-baseline commit

A **major** bump is not complete until a re-baseline commit exists. That commit:

1. re-runs the full dev split with the committed configuration and archives the
   new `results.json` as the baseline;
2. re-derives the committed thresholds in `ci/thresholds.yaml` from that run
   (dev split only — never the held-out split);
3. records the old threshold, the new threshold and the reason in the changelog.

Threshold *relaxation* to make a pull request pass remains prohibited
(`docs/EVALUATION.md` §18.4).

### Immutability

A published version is never edited in place. Typo fixes, clarifications and
label corrections are new versions. The manifest records the SHA-256 of every
released file, and the redaction/publish tooling refuses to build an artifact
whose files do not match the manifest counts.

---

## Unreleased

Nothing yet. The next version is expected to be `bench-v1.1`: the same item set
with the corpus captured, the gold templates replaced by captured values, a
second annotator's pass recorded, and Cohen's κ reported per class.
