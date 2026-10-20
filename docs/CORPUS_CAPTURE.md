# Corpus capture report

**Captured:** 2026-10-20 · **Manifest:** `data/manifests/nigeria_v1.yaml` (v2) · **Tool:** `python -m scholarmind.ingestion.capture`

This document records what a real capture of the Nigeria-first manifest actually
produced, including the failures. It is the honest state of the corpus, not a
plan for it.

## Outcome

| Metric | Value |
|---|---|
| Manifest entries | 33 |
| Pages captured (direct fetch) | 90 of 104 attempted (26 entries + crawled child pages) |
| Entries needing a headless render | 4 (all Chevening pages) |
| Entries unreachable from this network | 5 (DNS failure or timeout) |
| Entries bot-blocked (403) | 3 (Oxford, Cambridge, Edinburgh) |
| Trust signals raised | 28 |
| Facts extracted (deadline/opening) | 26 |
| Eligibility rules extracted | 2 typed rules |
| Funding components extracted | 51 |
| Required documents extracted | 9 |

## The three findings that matter

### 1. The highest-value sources are JavaScript-rendered

Chevening - the single most important scholarship for Nigerian postgraduates -
serves its eligibility criteria as rendered content. A plain HTTP fetch returns
7,276 characters of navigation, a country list and no requirements at all. The
static HTML contains the words "eligible" zero times.

The platform therefore treats this as a first-class source property rather than
a bug: manifest entries carry `requires_render: true`, and
`scholarmind/ingestion/browser.py` provides a Playwright-backed renderer that
feeds the same pipeline through the same client interface. Rendering is optional
and its absence is reported, never hidden.

**Consequence for the research plan:** a corpus built only from static fetches
would systematically exclude the funders with the most detailed, most contested
requirements - precisely the rules where eligibility reasoning matters most.

### 2. Roughly a third of the corpus is unreachable from a data-centre network

Five entries did not resolve or timed out, and three university pages return
403 to any client. This is an environmental property, not a code defect: the
URLs are correct. Such sources are marked `fetch_policy: manual` or `browser`
in the manifest so the next operator knows a manual capture (with provenance)
or a rendered capture is required.

The trust module records the cause rather than silently skipping the source -
a certificate that does not match its hostname (`ptdf.gov.ng` on `www`) becomes
a `tls_anomaly` signal rather than a silently ignored error.

### 3. Rule-based extraction alone recovers little from landing pages

Against 90 real captured pages, the deterministic extractor produced 26 dated
facts, 51 funding components, 9 required documents and only 2 typed eligibility
rules. The reason is that landing pages are navigation, and eligibility rules
live one or two clicks deeper.

This is the empirical case for the platform's central design decision: a
rule-based extractor can be precise but not complete, so the pipeline needs a
model-assisted extraction stage whose proposals are validated against the same
span rules before they are stored. The deterministic extractor is the fallback
and the safety net, not the whole story.

## What the capture changed in the code

- **Allow-listing by registrable domain.** The first manifest fetch failed on
  ordinary `www` -> apex redirects (`ndpc.gov.ng`, `mastercardfdn.org`). The
  allowlist now compares registrable domains, with an explicit list of
  multi-label public suffixes (`gov.ng`, `ac.uk`, `co.za`, ...) so that two
  unrelated government sites are never collapsed into one.
- **Link discovery.** `capture --crawl-depth N` follows in-domain links whose
  path looks fact-bearing (eligibility, funding, application, deadline). This
  is what moved the Chevening landing pages from zero facts to the eligibility
  and timeline pages.
- **TLS anomalies as trust signals.** Certificate problems are recorded against
  the source and demote its effective trust tier; TLS verification is never
  weakened.
- **Extraction patterns tuned against real text.** "at least two years of work
  experience", "must have lived in your country of residence for at least one
  year", "minimum score of 6.5 in IELTS" and "proof of ..." are now recognised,
  because these are the phrasings the corpus actually contains.

## Reproducing

```bash
python -m scholarmind.ingestion.capture \
    --manifest data/manifests/nigeria_v1.yaml \
    --output data/raw --delay 2 --crawl-depth 4
```

The raw captures are written under `data/raw/<host>_<n>/` with `page.html`,
`page.txt` and `capture.json` (URL, final URL, status, content hash, headers,
capture time and trust signals). `data/raw/capture_report.json` summarises the
run.

Raw captures are not committed: they are fetched again on demand, and the
content hashes in the capture report are what make a re-capture comparable to
the previous one.
