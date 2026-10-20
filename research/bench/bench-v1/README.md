# bench-v1

Release line `bench-v1`, version `bench-v1.0` (created 2026-10-20).

| File | Records | Notes |
|---|---|---|
| `questions.jsonl` | 36 | 6 per class; 24 `dev`, 12 `heldout` |
| `eligibility_pairs.jsonl` | 24 | 4 per edge case |
| `change_pairs.jsonl` | 20 | 6 of them controls (`old_value == new_value`) |
| `adversarial.jsonl` | 18 | 7 families; 9 items block a release |
| `manifest.json` | — | counts, distributions, annotation status, licence, SHA-256 per file |

Schemas for every field are in [`../DATASET_CARD.md`](../DATASET_CARD.md) §9.

## Verifying the items

**1. Structural check.** Every line is one JSON object; every record carries the
fields listed in the dataset card.

```bash
python -c "import json;[json.loads(l) for l in open('questions.jsonl',encoding='utf-8') if l.strip()]"
```

**2. Redaction check.** No page bodies, unapproved URLs, evidence markers or
contact addresses may be present.

```bash
python ../tools/redact.py --check
```

**3. Hash check.** The SHA-256 of each file must equal the value in
`manifest.json` under `content_hashes`.

```bash
python -c "import hashlib,json;m=json.load(open('manifest.json',encoding='utf-8'));\
print(*[(k,hashlib.sha256(open(k.split('/')[-1],'rb').read()).hexdigest()==v.split(':')[1]) for k,v in m['content_hashes'].items()],sep='\n')"
```

**4. Count and distribution check.** The publisher fails if the record counts
disagree with the manifest.

```bash
python ../tools/publish.py --dry-run
```

## How to verify an item by hand

Every item is currently **unverified** (`"verified": false`). To verify one:

1. Open the scholarship named by `scholarship_slug` in
   `data/manifests/nigeria_v1.yaml` and capture the page.
2. Read `notes` — it names the **exact field** to check on the official page
   (for example *"the application deadline field of the 2027 cycle on the
   official Chevening scholarships page"*).
3. Replace the template in `gold_answer` with the captured value, keeping the
   page's own wording, and record the evidence chunk id and the snapshot
   content hash.
4. Set `verified` to `true` only when the captured page supports the answer as
   written. Record the change as a new version (`CHANGELOG.md`), never as an
   edit to this directory.

### Why the gold answers look like specifications

`gold_answer` in this release describes *what the answer must be*, not a value
that was read off a page — the corpus has not been captured yet. For example,
a `fact` item specifies the 2027 deadline *as stated on the funder's official
page, in ISO format, with the page's own wording preserved*. Writing a
concrete date that no page has been read from would be a fabricated gold label,
and a system could be scored against it. The `insufficient` and `adversarial`
items are the exception: their gold answers are behavioural specifications
(what the system must do), which are fully determined by the protocol and do
not depend on a capture.

## Split discipline

* `dev` — 24 items, used for iteration and for every committed threshold.
* `heldout` — 12 items, run once per release. A held-out number never feeds a
  threshold (`docs/EVALUATION.md` §18.4).

## Controls and severity

`change_pairs.jsonl` contains 6 control pairs with identical `old_value` and
`new_value`. A change detector that raises an event on any of them counts
against the false-alarm rate, and the release gate requires that rate to stay
below 10% (`docs/EVALUATION.md` §9, R3). The 14 edited pairs carry an
`expected_severity` that a field-aware detector must reproduce.
