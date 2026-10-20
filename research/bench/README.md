# ScholarBench-Africa

Public release of the ScholarMind gold set: a versioned, citable benchmark for
scholarship search, eligibility reasoning, abstention and change detection over
African scholarship sources.

* **Dataset card:** [`DATASET_CARD.md`](DATASET_CARD.md) — purpose, source policy,
  annotation protocol, known limitations, schemas, citation.
* **Changelog and versioning policy:** [`CHANGELOG.md`](CHANGELOG.md).
* **Release contents:** [`bench-v1/`](bench-v1/) — `bench-v1.0`.

## Layout

```
research/bench/
├── README.md              # this file
├── DATASET_CARD.md         # dataset card
├── CHANGELOG.md            # version history and versioning policy
├── bench-v1/               # one directory per release; immutable once published
│   ├── questions.jsonl     # 36 gold questions
│   ├── eligibility_pairs.jsonl  # 24 (profile, scholarship) pairs
│   ├── change_pairs.jsonl  # 20 before/after snapshot pairs (6 controls)
│   ├── adversarial.jsonl   # 18 adversarial items
│   ├── manifest.json       # counts, distributions, hashes, licence
│   └── README.md           # how to verify the items
└── tools/
    ├── redact.py           # release redaction check
    ├── publish.py          # release builder
    └── __init__.py
```

## Redaction check

The release must not contain page bodies, unapproved URLs, evidence markers or
contact addresses. The check is the last gate before publication and is run on
every release.

```bash
# from the repository root
python research/bench/tools/redact.py --check
```

* exit `0` — clean; exit `1` — findings (each is printed with file, path and
  reason).
* `--json` emits the report as JSON for CI consumption.
* `--path <file>` scans a specific file instead of the default release set.
* `--bench-dir <dir>` points the tool at a different bench directory.

The checks are: field over 2000 characters; evidence markers
(`<<<EVIDENCE` and friends) or a contiguous run of 300 or more characters (the
shape of a copied paragraph); a key named `raw_content`, `extracted_text`,
`content` or `page_text` outside the allowlist; a URL whose host is not one of
the official domains in `data/manifests/nigeria_v1.yaml`; and an e-mail address
outside a reserved example domain.

## Publish a release

```bash
# report what would be written, without writing anything
python research/bench/tools/publish.py --dry-run

# build the artifact
python research/bench/tools/publish.py
```

The publisher reads `bench-v1/`, validates every record against the schema
documented in the dataset card, runs the redaction check, computes the SHA-256
of every release file and writes:

* `research/bench/dist/bench-v1-1.0.jsonl` — the merged release, one record per
  line, each tagged with `dataset_version` and `release_file`;
* `research/bench/dist/bench-v1-1.0.manifest.json` — the release summary,
  including per-file hashes, item counts and the redaction result.

Exit code `1` means validation or redaction failed and **nothing was written**.

## Current status

`bench-v1.0` is a scaffold release. **No item is verified**: the source corpus
has not been captured yet, so every record carries `"verified": false` and every
gold answer is a template naming the field to check on the official page. The
release is usable for harness and tooling development; it is not usable for
reporting accuracy numbers. See `DATASET_CARD.md` §6.

## Conventions

* JSONL: one compact JSON object per line, UTF-8, LF endings, no trailing commas.
* Versions are `bench-v<line>.<minor>`. A published version is never edited in
  place — corrections are new versions (see `CHANGELOG.md`).
* Tooling: Python standard library only, type hints, `from __future__ import annotations`.
