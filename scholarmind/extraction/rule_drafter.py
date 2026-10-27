"""Draft eligibility rules with an LLM, then validate them mechanically.

This is the propose-then-review half of rule extraction. A language model reads
an eligibility passage and proposes structured rule candidates; a validator
rejects every candidate whose span does not sit inside the source text or whose
claimed values are not literally present in the quoted passage. Only candidates
that survive validation enter the review queue, and only rules a human approves
reach the eligibility engine. The model never decides eligibility: it drafts,
a person signs off.

Design rules
------------
* The drafter depends only on the ``GenerationProvider`` protocol from the core
  package, so tests run it against a fake provider and the application layer
  binds the real one.
* ``rule_text`` must appear exactly in the source. Character spans are computed
  by locating that quote in the source (the model does not emit spans), which
  cannot drift the way model-computed indices can.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from scholarmind.generation.provider import (
    GenerationProvider,
    GenerationRequest,
    Message,
)

# The rule kinds and profile subjects the eligibility engine can evaluate.
# A candidate outside this table is rejected rather than silently relaxed, so
# the queue only ever holds rules the engine understands.
RULE_KINDS: dict[str, dict[str, Sequence[str]]] = {
    "nationality": {"subjects": ("nationality", "citizenship")},
    "residency": {"subjects": ("residency", "country_of_residence")},
    "degree_level": {"subjects": ("degree_level", "current_degree_level")},
    "gpa": {"subjects": ("gpa.min_overall", "gpa.min_major")},
    "work_experience": {"subjects": ("work_experience.years",)},
    "english_proficiency": {"subjects": ("english.score", "english.test")},
    "discipline": {"subjects": ("discipline", "field_of_study")},
    "age": {"subjects": ("age.years",)},
}

VALID_OPERATORS = ("equals", "not_equals", "in", "not_in", "gte", "lte", "between", "required")

# `required` means "must provide X" - there is nothing to quote as a value.
_VALUELESS_OPERATORS = frozenset(("required",))

# The extractor normalises values (country names become ISO codes) before a
# candidate is stored. That is a deterministic transformation, not a model
# decision, but it means the stored value no longer literally appears in the
# quote - the reviewer sees both the quote and the normalised value.
VALUE_NORMALISED_NOTE = "value_normalised_by_extractor"

_PROMPT_SCHEMA = """\
Allowed rule kinds and the profile subject each kind may use:
{schema}

Allowed operators: {operators}.
Value formats by kind:
- nationality / residency / discipline: a list of country or field names, e.g.
  {{"operator": "in", "value": ["Nigeria", "Ghana"]}}
- degree_level: a list from bachelors, masters, doctorate, higher_diploma
- gpa / english_proficiency: one number, e.g. {{"operator": "gte", "value": 3.0}}
- work_experience: years as one number, e.g. {{"operator": "gte", "value": 2}}
- age: one number for gte/lte, or a two-item list for between
"""

_SYSTEM_PROMPT = """\
You convert scholarship eligibility prose into structured rule candidates for a
human reviewer. Rules:
1. Propose ONLY requirements that are literally and unambiguously stated in the
   passage below. If the wording is vague ("preference will be given to
   research experience"), do not propose it.
2. "rule_text" MUST be copied word for word from the passage - it is verified
   against the source and any paraphrase is rejected.
3. Any value you state (a threshold, a country name, a degree class) MUST
   appear inside that same quoted text.
4. Never invent values. Never merge two requirements into one rule.
5. Output ONLY a JSON array, possibly empty. Each item:
   {"kind": ..., "subject": ..., "operator": ..., "value": ...,
    "mandatory": true, "rule_text": "..."}
   "mandatory" is false only when the passage clearly marks the condition as
   optional or as a preference.
6. When nothing qualifies, return [].
"""


@dataclass
class DraftCandidate:
    """One proposed rule, span-anchored to the passage it came from."""

    kind: str
    subject: str
    operator: str
    rule_text: str
    span_start: int
    span_end: int
    value: Any = None
    mandatory: bool = True
    confidence: float = 0.0

    def to_record(self) -> dict[str, Any]:
        """Serialisable representation for persistence."""
        return {
            "kind": self.kind,
            "subject": self.subject,
            "operator": self.operator,
            "rule_text": self.rule_text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "value": self.value,
            "mandatory": self.mandatory,
            "confidence": self.confidence,
        }


@dataclass
class DraftOutcome:
    """Result of one drafting pass over one passage."""

    candidates: list[DraftCandidate] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    parse_error: str | None = None

    @property
    def accepted_count(self) -> int:
        return len(self.candidates)


def build_draft_messages(source_text: str) -> list[Message]:
    """Build the chat messages for one drafting request."""
    schema = _PROMPT_SCHEMA.format(
        schema="\n".join(f"- {kind}: {meta['subjects']}" for kind, meta in RULE_KINDS.items()),
        operators=", ".join(VALID_OPERATORS),
    )
    return [
        Message(role="system", content=_SYSTEM_PROMPT + "\n" + schema),
        Message(role="user", content=f"Passage:\n\"\"\"\n{source_text}\n\"\"\"\nJSON array:"),
    ]


def validate_value_in_text(value: Any, rule_text: str) -> bool:
    """Check that the claimed value is literally present in the quoted rule.

    Numbers match on an exact rendered form and also accept a value embedded in
    a hyphenated range ("6.0 - 7.0"); names match case-insensitively on a
    whitespace-collapsed copy. `required` / `absent` rules carry no value.
    """
    if value is None:
        return True

    folded = re.sub(r"\s+", " ", rule_text).lower()
    folded = folded.replace("-", " ").replace("–", " ").replace("–", " ")

    def _contains(needle: str) -> bool:
        n = re.sub(r"\s+", " ", needle).strip().lower().replace("-", " ")
        return bool(n) and n in folded

    if isinstance(value, (list, tuple)):
        return all(_contains(str(item)) for item in value)
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        rendered = str(int(value)) if float(value).is_integer() else str(value)
        return _contains(rendered)
    return _contains(str(value))


def validate_rule_shape(
    *,
    kind: str,
    subject: str,
    operator: str,
    value: Any = None,
    quote: str | None = None,
    values_normalised: bool = False,
) -> list[str]:
    """Return every reason a rule's shape (and optional quote) fails.

    ``quote`` is the source text the rule was extracted from. When given and
    ``values_normalised`` is False, every claimed value must appear literally
    in the quote - the reviewer sees exactly what the source said. When
    ``values_normalised`` is True the values went through a deterministic
    normaliser (for example country names to ISO codes), so literal containment
    cannot be checked and only the shape is validated.
    """
    errors: list[str] = []
    if kind not in RULE_KINDS:
        errors.append(f"unknown rule kind: {kind!r}")
        return errors
    allowed_subjects = RULE_KINDS[kind]["subjects"]
    if subject not in allowed_subjects:
        errors.append(
            f"subject {subject!r} is not valid for kind {kind!r} (expected one of {list(allowed_subjects)})"
        )
        return errors
    if operator not in VALID_OPERATORS:
        errors.append(f"unknown operator: {operator!r}")
        return errors
    if value is None and operator not in _VALUELESS_OPERATORS:
        errors.append(f"operator {operator!r} requires a value")
        return errors
    if quote is not None and not values_normalised and value is not None:
        if not validate_value_in_text(value, quote):
            errors.append(f"claimed value {value!r} is not contained in the quoted rule text")
    return errors


def validate_candidate(
    candidate: DraftCandidate,
    source_text: str,
    *,
    span_start: int | None = None,
    span_end: int | None = None,
    rule_text: str | None = None,
    kind: str | None = None,
    subject: str | None = None,
    operator: str | None = None,
    value: Any = None,
) -> list[str]:
    """Return every reason the candidate fails mechanical validation.

    Empty list means the candidate is span-anchored and value-faithful. The
    keyword arguments let the caller validate an edited candidate against the
    span stored at draft time without mutating the original.
    """
    k = kind if kind is not None else candidate.kind
    s = subject if subject is not None else candidate.subject
    o = operator if operator is not None else candidate.operator
    v = value if value is not None else candidate.value
    t = rule_text if rule_text is not None else candidate.rule_text
    start = span_start if span_start is not None else candidate.span_start
    end = span_end if span_end is not None else candidate.span_end

    errors: list[str] = []
    if not t or not t.strip():
        errors.append("rule_text is empty")
        return errors
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        errors.append("span bounds are not a non-empty range")
        return errors
    if end > len(source_text):
        errors.append("span end is outside the source text")
        return errors
    if source_text[start:end] != t:
        errors.append("span does not reproduce rule_text exactly")
        return errors
    errors.extend(
        validate_rule_shape(kind=k, subject=s, operator=o, value=v, quote=t)
    )
    return errors


def _locate_span(rule_text: str, source_text: str) -> tuple[int, int] | None:
    """Find the quote in the source and return ITS true span."""
    if not rule_text or len(rule_text) < 3:
        return None
    index = source_text.find(rule_text)
    if index == -1:
        return None
    return index, index + len(rule_text)


def _parse_json_array(response_text: str) -> list[Any] | dict[str, Any]:
    """Parse a JSON array (or an object carrying one) from a model response.

    Models wrap JSON in prose or code fences; this extracts the outermost array.
    Raises ``ValueError`` when nothing parseable is present so the caller can
    count the attempt as a parse failure rather than silently accept nothing.
    """
    candidate = (response_text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
    for opener, closer in (("[", "]"), ("{", "}")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON array or object found in the response")


def parse_draft_response(response_text: str, source_text: str) -> DraftOutcome:
    """Turn one provider response into validated candidates."""
    outcome = DraftOutcome()
    try:
        items = _parse_json_array(response_text)
    except ValueError as exc:
        outcome.parse_error = f"parse failed: {exc}"
        return outcome

    if isinstance(items, dict):
        items = items.get("candidates", [])
    if not isinstance(items, list):
        outcome.parse_error = "response is not a JSON array"
        return outcome

    for raw in items:
        if not isinstance(raw, dict):
            outcome.rejected.append({"reason": "item is not an object", "item": raw})
            continue
        rule_text = raw.get("rule_text", "")
        span = _locate_span(rule_text, source_text)
        candidate = DraftCandidate(
            kind=str(raw.get("kind", "")),
            subject=str(raw.get("subject", "")),
            operator=str(raw.get("operator", "")),
            value=raw.get("value"),
            mandatory=bool(raw.get("mandatory", True)),
            rule_text=rule_text,
            span_start=span[0] if span else -1,
            span_end=span[1] if span else -1,
            confidence=float(raw.get("confidence", 0.5)),
        )
        errors = validate_candidate(candidate, source_text)
        if errors:
            outcome.rejected.append({"reason": errors, "item": candidate.to_record()})
        else:
            outcome.candidates.append(candidate)
    return outcome


def draft_rules_for_text(
    provider: GenerationProvider,
    source_text: str,
    *,
    model: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> DraftOutcome:
    """Ask the provider to draft rule candidates for one passage and validate.

    Validation is the gate: a candidate whose quote cannot be located in the
    source, or whose values are not literally in that quote, never leaves this
    function as an accepted candidate.
    """
    request_messages = build_draft_messages(source_text)
    response = provider.generate(
        GenerationRequest(
            messages=request_messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )
    outcome = parse_draft_response(response.text, source_text)
    return outcome
