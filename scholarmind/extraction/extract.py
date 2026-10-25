"""Rule-based fact extraction from captured source text.

This extractor is deterministic and dependency-free, so it can run on every
snapshot, be unit tested, and serve as the fallback when a model-assisted
extraction is unavailable or fails validation.

It is intentionally conservative: it extracts what it can anchor to a span and
leaves everything else for the review queue. An LLM-assisted extractor may
propose additional facts (see ``scholarmind/extraction/llm.py``), but proposed
facts are validated against the same span rules before they are stored.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from scholarmind.extraction.schema import (
    ClaimType,
    DocumentFact,
    EligibilityFact,
    ExtractionResult,
    Fact,
    FactStatus,
    FundingFact,
)
from scholarmind.normalization.dates import parse_datetime
from scholarmind.normalization.fields import (
    normalise_degree_level,
    normalise_document_type,
    normalise_funding_component,
)

DEADLINE_HINTS = (
    "closing date",
    "application deadline",
    "applications close",
    "deadline",
    "submit your application by",
    "last date",
    "applications must be submitted",
)

FUNDING_HINTS = (
    "full tuition",
    "tuition fees",
    "tuition fee",
    "living allowance",
    "monthly stipend",
    "annual stipend",
    "stipend",
    "travel allowance",
    "airfare",
    "accommodation",
    "housing",
    "medical insurance",
    "insurance",
    "fully funded",
    "full funding",
)

DOCUMENT_HINTS = (
    "required documents",
    "documents required",
    "you must submit",
    "supporting documents",
    "the following documents",
    "application documents",
)

ELIGIBILITY_HINTS = (
    "eligibility criteria",
    "eligibility requirements",
    "who can apply",
    "applicants must",
    "applicants should",
    "candidates must",
    "you must have",
    "must be aged",
    "must be between",
    "must hold",
    "must have",
    "must not",
    "must be",
    "required to",
    "need to meet",
    "needs to meet",
    "are eligible",
    "is eligible",
    "eligible if",
    "open to",
    "citizens of",
    "nationals of",
    "minimum age",
    "at least",
    "score of",
    "requirements:",
    "criteria:",
)

# "at least two years of work experience" and its many variants.
WORK_EXPERIENCE_RE = re.compile(
    r"(?:at\s+least|minimum\s+of|no\s+less\s+than)\s+(\d{1,2})\s*(?:\(\d+\))?\s*"
    r"year[s]?\s+(?:of\s+)?(?:full[-\s]time\s+|relevant\s+|professional\s+|work\s+|hands[-\s]on\s+)*experience",
    re.IGNORECASE,
)

# "you must have lived in your country of residence for at least one year"
RESIDENCY_YEARS_RE = re.compile(
    r"(?:have\s+lived|reside|living|residing)\s+in\s+[^.]{0,60}?for\s+at\s+least\s+(\d{1,2})\s*year",
    re.IGNORECASE,
)

# "proof of X", "a certificate of X", "transcript of X"
PROOF_RE = re.compile(
    r"(?:proof|certificate|transcript|certification)\s+of\s+([a-z][a-z\s\-]{3,45})",
    re.IGNORECASE,
)

MINIMUM_ENGLISH_RE = re.compile(
    r"(?:minimum|at\s+least|no\s+less\s+than)\s+(?:score\s+of\s+|band\s+of\s+|grade\s+of\s+)?"
    r"(\d{1,2}(?:\.\d)?)\s*(?:in|for|,)?\s*(IELTS|TOEFL)",
    re.IGNORECASE,
)

NATIONALITY_RE = re.compile(
    r"(?:citizens?|nationals?)\s+of\s+(?P<list>[^.\n;]{2,140})",
    re.IGNORECASE,
)
AGE_RE = re.compile(
    r"(?:aged|age(?:d)?)\s+(?:between\s+)?(\d{1,2})\s*(?:to|-|–|and)\s*(\d{1,2})",
    re.IGNORECASE,
)
AGE_MAX_RE = re.compile(r"(?:not\s+(?:more|older)\s+than|under|below)\s+(\d{2})\s+years?\s+old", re.IGNORECASE)
AGE_MIN_RE = re.compile(r"(?:at\s+least|minimum\s+age\s+of)\s+(\d{2})\s+years?\s+old", re.IGNORECASE)
DEGREE_RE = re.compile(
    r"(?:bachelor'?s?|master'?s?|mba|phd|doctorate|postgraduate|undergraduate)\s+degree",
    re.IGNORECASE,
)
ENGLISH_TEST_RE = re.compile(r"(IELTS|TOEFL)", re.IGNORECASE)
ENGLISH_SCORE_RE = re.compile(r"(IELTS|TOEFL)[^.\n]{0,60}?(\d{1,2}(?:\.\d)?)\s*(?:or\s*(?:above|higher))?", re.IGNORECASE)

COVERAGE_PHRASES = (
    ("included", "included"),
    ("covers", "included"),
    ("covering", "included"),
    ("includes", "included"),
    ("excluded", "excluded"),
    ("does not cover", "excluded"),
    ("not cover", "excluded"),
    ("will not pay", "excluded"),
    ("conditional", "conditional"),
    ("subject to", "conditional"),
    ("depending on", "conditional"),
)


def _iter_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield (offset, line) for each line of the text."""
    offset = 0
    for line in text.splitlines():
        yield offset, line
        offset += len(line) + 1


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Split text into sentence-ish spans with their offsets.

    Lines are processed individually so that bullet lists (a document list
    under an introduction, for example) yield one span per item instead of
    being swallowed by a paragraph.
    """
    spans: list[tuple[int, int, str]] = []
    for line_match in re.finditer(r"[^\n]*\n?", text):
        line = line_match.group(0)
        base = line_match.start()
        for sentence_match in re.finditer(r"[^.!?]*[.!?]?", line):
            raw = sentence_match.group(0)
            stripped = raw.strip()
            if len(stripped) < 12:
                continue
            leading = len(raw) - len(raw.lstrip())
            start = base + sentence_match.start() + leading
            spans.append((start, start + len(stripped), stripped))
    return spans


OPENING_HINTS = ("applications open", "opening date", "applications are open", "opens on", "opening of applications")


def _hint_positions(sentence: str) -> list[tuple[int, str]]:
    """Locate deadline/opening hints in a sentence, with their offsets."""
    positions: list[tuple[int, str]] = []
    lowered = sentence.lower()
    for hint in OPENING_HINTS:
        index = lowered.find(hint)
        if index != -1:
            positions.append((index, "opening"))
    for hint in DEADLINE_HINTS:
        index = lowered.find(hint)
        if index != -1:
            positions.append((index, "deadline"))
    return sorted(positions)


def extract_deadlines(text: str) -> list[Fact]:
    """Extract deadlines and opening dates with their spans.

    A sentence may carry more than one date ("Applications open on 4 August
    2026 and the application deadline is 12 November 2026"). Each date is
    assigned to the nearest preceding hint so the opening date is never
    mistaken for the deadline.
    """
    from scholarmind.normalization.dates import find_dates

    facts: list[Fact] = []
    seen: set[tuple[str, str]] = set()

    for start, end, sentence in _sentence_spans(text):
        lowered = sentence.lower()
        hints = _hint_positions(sentence)
        if not hints:
            continue

        occurrences = find_dates(sentence)
        if not occurrences:
            facts.append(
                Fact(
                    claim_type=ClaimType.DEADLINE,
                    text=sentence,
                    span_start=start,
                    span_end=end,
                    normalized_value=None,
                    field_name="deadline_raw_text",
                    confidence=0.35,
                    status=FactStatus.UNRESOLVED,
                    extraction_method="rule",
                    notes=["A deadline sentence was found but no date could be parsed from it."],
                )
            )
            continue

        for date_start, date_end, value in occurrences:
            preceding = [kind for position, kind in hints if position <= date_start]
            if preceding:
                kind = preceding[-1]
            else:
                # Table rows and timelines put the label after the date
                # ("1 April 2026 - Applications open"). Use the next hint
                # rather than defaulting to the first one on the line.
                following = [kind for position, kind in hints if position >= date_start]
                kind = following[0] if following else hints[0][1]

            precision = "exact"
            if re.match(r"^[A-Za-z]+$", sentence[date_start:date_end].strip()) or len(sentence[date_start:date_end].strip()) <= 4:
                precision = "month"

            key = (value.isoformat(), kind)
            if key in seen:
                continue
            seen.add(key)

            facts.append(
                Fact(
                    claim_type=ClaimType.OPENING_DATE if kind == "opening" else ClaimType.DEADLINE,
                    text=sentence,
                    span_start=start,
                    span_end=end,
                    normalized_value={
                        "value": value.isoformat(),
                        "precision": precision,
                        "raw_text": sentence[date_start:date_end],
                        "timezone": None,
                    },
                    field_name="opens_at" if kind == "opening" else "deadline_at",
                    confidence=0.85 if precision == "exact" else 0.6,
                    status=FactStatus.CONFIRMED if precision == "exact" else FactStatus.AMBIGUOUS,
                    extraction_method="rule",
                    notes=[] if precision == "exact" else [f"Date precision is '{precision}'."],
                )
            )
    return facts


def extract_funding(text: str) -> list[FundingFact]:
    """Extract funding components, keeping per-component coverage status."""
    funding: dict[str, FundingFact] = {}

    for start, end, sentence in _sentence_spans(text):
        lowered = sentence.lower()
        if not any(hint in lowered for hint in FUNDING_HINTS):
            continue

        coverage = "unknown"
        for phrase, mapped in COVERAGE_PHRASES:
            if phrase in lowered:
                coverage = mapped
                break

        if "fully funded" in lowered or "full funding" in lowered:
            # A blanket "fully funded" claim does not make every component
            # included; it is recorded as a general funding fact instead.
            continue

        for component in (
            "tuition",
            "stipend",
            "travel",
            "accommodation",
            "insurance",
            "equipment",
            "research",
        ):
            normalised = normalise_funding_component(component)
            if not normalised:
                continue
            if normalised not in lowered:
                continue
            if normalised in funding:
                continue
            funding[normalised] = FundingFact(
                component=normalised,
                coverage=coverage,
                rule_text=sentence,
                span_start=start,
                span_end=end,
                confidence=0.7 if coverage != "unknown" else 0.4,
            )

    for component, phrase in (
        ("tuition", ("tuition", "school fees")),
        ("stipend", ("stipend", "living allowance", "maintenance allowance")),
        ("travel", ("travel", "airfare", "flight")),
        ("accommodation", ("accommodation", "housing", "hostel")),
        ("insurance", ("insurance",)),
    ):
        normalised = normalise_funding_component(component)
        if normalised and normalised not in funding:
            for hint in phrase:
                for start, end, sentence in _sentence_spans(text):
                    if hint in sentence.lower() and normalised in sentence.lower():
                        funding[normalised] = FundingFact(
                            component=normalised,
                            coverage="unknown",
                            rule_text=sentence,
                            span_start=start,
                            span_end=end,
                            confidence=0.4,
                        )
                        break
                if normalised in funding:
                    break
    return list(funding.values())


def extract_documents(text: str) -> list[DocumentFact]:
    """Extract required documents from list-like sections.

    Documents are often listed as bare bullet items under an introductory
    sentence ("You must submit the following documents:"), so a document item is
    accepted when it appears within a window after such an introduction.
    """
    documents: dict[str, DocumentFact] = {}

    hint_positions = [
        match.start()
        for hint in DOCUMENT_HINTS
        for match in re.finditer(re.escape(hint), text, re.IGNORECASE)
    ]
    window = 900

    for start, end, sentence in _sentence_spans(text):
        lowered = sentence.lower()
        doc_type = normalise_document_type(sentence)
        if not doc_type:
            continue

        near_hint = any(start - window <= position <= end + 60 for position in hint_positions)
        inline_hint = any(hint in lowered for hint in ("required", "must submit", "submit a", "provide a"))
        if not (near_hint or inline_hint):
            continue

        mandatory = not any(phrase in lowered for phrase in ("if applicable", "optional", "where applicable"))
        if doc_type in documents:
            continue

        proof = PROOF_RE.search(sentence)
        if proof and not doc_type:
            from scholarmind.normalization.fields import normalise_document_type as _normalise

            doc_type = _normalise(proof.group(1))
            if not doc_type:
                continue

        documents[doc_type] = DocumentFact(
            doc_type=doc_type,
            mandatory=mandatory,
            description=sentence.strip()[:280],
            rule_text=sentence,
            span_start=start,
            span_end=end,
            requires_notarization="notaris" in lowered or "notariz" in lowered,
            requires_apostille="apostille" in lowered,
            requires_credential_evaluation="credential evaluation" in lowered,
            confidence=0.7,
        )
    return list(documents.values())


def extract_eligibility(text: str) -> list[EligibilityFact]:
    """Extract eligibility conditions the rule engine can evaluate."""
    rules: list[EligibilityFact] = []

    for start, end, sentence in _sentence_spans(text):
        lowered = sentence.lower()
        if not any(hint in lowered for hint in ELIGIBILITY_HINTS):
            continue
        if len(sentence) < 25:
            continue

        nationality = NATIONALITY_RE.search(sentence)
        if nationality:
            from scholarmind.normalization.fields import normalise_country

            raw_list = nationality.group("list")
            countries: list[str] = []
            for token in re.split(r",|\band\b|/|\bor\b", raw_list):
                token = token.strip(" .;:()")
                if not token:
                    continue
                code = normalise_country(token)
                if code and code not in countries:
                    countries.append(code)
            if countries:
                rules.append(
                    EligibilityFact(
                        kind="nationality",
                        subject="nationality",
                        operator="in",
                        value=countries,
                        rule_text=sentence.strip(),
                        span_start=start,
                        span_end=end,
                        parseable=True,
                        confidence=0.75,
                    )
                )
            else:
                rules.append(
                    EligibilityFact(
                        kind="nationality",
                        subject="nationality",
                        operator="in",
                        value=[raw_list.strip()],
                        rule_text=sentence.strip(),
                        span_start=start,
                        span_end=end,
                        parseable=False,
                        confidence=0.4,
                        notes=[f"Nationality list '{raw_list.strip()}' could not be normalised."],
                    )
                )

        age_range = AGE_RE.search(sentence)
        if age_range:
            rules.append(
                EligibilityFact(
                    kind="age",
                    subject="age.max",
                    operator="between",
                    value=[int(age_range.group(1)), int(age_range.group(2))],
                    rule_text=sentence.strip(),
                    span_start=start,
                    span_end=end,
                    confidence=0.8,
                )
            )
        else:
            age_max = AGE_MAX_RE.search(sentence)
            if age_max:
                rules.append(
                    EligibilityFact(
                        kind="age",
                        subject="age.max",
                        operator="lte",
                        value=int(age_max.group(1)),
                        rule_text=sentence.strip(),
                        span_start=start,
                        span_end=end,
                        confidence=0.8,
                    )
                )
            age_min = AGE_MIN_RE.search(sentence)
            if age_min:
                rules.append(
                    EligibilityFact(
                        kind="age",
                        subject="age.min",
                        operator="gte",
                        value=int(age_min.group(1)),
                        rule_text=sentence.strip(),
                        span_start=start,
                        span_end=end,
                        confidence=0.8,
                    )
                )

        degree = DEGREE_RE.search(sentence)
        if degree:
            level = normalise_degree_level(degree.group(0))
            if level:
                rules.append(
                    EligibilityFact(
                        kind="degree_level",
                        subject="degree_level",
                        operator="equals",
                        value=level,
                        rule_text=sentence.strip(),
                        span_start=start,
                        span_end=end,
                        confidence=0.7,
                    )
                )

        english_score = ENGLISH_SCORE_RE.search(sentence)
        minimum_english = MINIMUM_ENGLISH_RE.search(sentence)
        if english_score:
            test = english_score.group(1).upper()
            score = float(english_score.group(2))
        elif minimum_english:
            score = float(minimum_english.group(1))
            test = minimum_english.group(2).upper()
        if english_score or minimum_english:
            rules.append(
                EligibilityFact(
                    kind="language",
                    subject="ielts" if test == "IELTS" else "toefl",
                    operator="gte",
                    value=score,
                    rule_text=sentence.strip(),
                    span_start=start,
                    span_end=end,
                    confidence=0.7,
                )
            )

        experience = WORK_EXPERIENCE_RE.search(sentence)
        if experience:
            months = int(experience.group(1)) * 12
            rules.append(
                EligibilityFact(
                    kind="work_experience",
                    subject="work_experience_months",
                    operator="gte",
                    value=months,
                    rule_text=sentence.strip(),
                    span_start=start,
                    span_end=end,
                    confidence=0.75,
                )
            )

        residency = RESIDENCY_YEARS_RE.search(sentence)
        if residency:
            months = int(residency.group(1)) * 12
            rules.append(
                EligibilityFact(
                    kind="residency",
                    subject="residency_months",
                    operator="gte",
                    value=months,
                    rule_text=sentence.strip(),
                    span_start=start,
                    span_end=end,
                    confidence=0.7,
                )
            )

    return rules


def extract_all(text: str) -> ExtractionResult:
    """Run every rule-based extractor over a snapshot's text."""
    result = ExtractionResult(extraction_method="rule")
    result.facts.extend(extract_deadlines(text))
    result.funding.extend(extract_funding(text))
    result.documents.extend(extract_documents(text))
    result.eligibility.extend(extract_eligibility(text))
    return result


def summarise(result: ExtractionResult) -> dict[str, Any]:
    """Counts by claim type, for extraction reports."""
    by_type: dict[str, int] = {}
    for fact in result.facts:
        by_type[fact.claim_type.value] = by_type.get(fact.claim_type.value, 0) + 1
    return {
        "facts": len(result.facts),
        "by_claim_type": by_type,
        "eligibility_rules": len(result.eligibility),
        "funding_components": len(result.funding),
        "required_documents": len(result.documents),
        "low_confidence": result.low_confidence_count,
    }
