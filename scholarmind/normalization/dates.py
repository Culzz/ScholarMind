"""Date extraction and normalisation.

Deadlines are stored as dates, never as prose. When the source states a date
only to the month or the year, the precision is recorded alongside the value so
the UI can say "by March 2027" rather than inventing a day. The raw source
wording is always kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

MONTH_NAMES = [name for name in sorted(MONTHS, key=len, reverse=True) if len(name) > 2]

# "12 March 2027", "12th March 2027", "March 12, 2027"
DAY_FIRST_RE = re.compile(
    r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]{3,9})\.?\s*,?\s*(?P<year>\d{4})\b"
)
MONTH_FIRST_RE = re.compile(
    r"\b(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(?P<year>\d{4})\b"
)
ISO_RE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
MONTH_YEAR_RE = re.compile(r"\b(?P<month>[A-Za-z]{3,9})\.?\s*,?\s*(?P<year>\d{4})\b")
NUMERIC_RE = re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})\b")


@dataclass(frozen=True)
class ParsedDate:
    """A date parsed from source text, with its precision."""

    value: date | None
    precision: str  # exact | day | month | year | unknown
    raw_text: str
    timezone: str | None = None
    is_datetime: bool = False

    def to_record(self) -> dict[str, Any]:
        return {
            "value": self.value.isoformat() if self.value else None,
            "precision": self.precision,
            "raw_text": self.raw_text,
            "timezone": self.timezone,
        }


def _month_number(name: str) -> int | None:
    return MONTHS.get(name.lower().rstrip("."))


def find_dates(text: str) -> list[tuple[int, int, date]]:
    """Find every date in ``text`` with its character span.

    Used when a single sentence contains more than one date (an opening date
    and a deadline, for example) so each date can be assigned to the hint that
    precedes it.
    """
    found: list[tuple[int, int, date]] = []
    patterns = (
        (ISO_RE, lambda m: date(int(m.group("year")), int(m.group("month")), int(m.group("day")))),
        (
            DAY_FIRST_RE,
            lambda m: date(int(m.group("year")), MONTHS[m.group("month").lower().rstrip(".")], int(m.group("day"))),
        ),
        (
            MONTH_FIRST_RE,
            lambda m: date(int(m.group("year")), MONTHS[m.group("month").lower().rstrip(".")], int(m.group("day"))),
        ),
    )
    for pattern, builder in patterns:
        for match in pattern.finditer(text):
            try:
                value = builder(match)
            except (KeyError, ValueError):
                continue
            found.append((match.start(), match.end(), value))

    found.sort(key=lambda item: item[0])
    deduped: list[tuple[int, int, date]] = []
    for span in found:
        if deduped and span[0] < deduped[-1][1]:
            continue
        deduped.append(span)
    return deduped


def parse_date(text: str, *, reference_year: int | None = None) -> ParsedDate:
    """Parse the first recognisable date in ``text``.

    ``reference_year`` is used for ambiguous numeric dates such as ``03/04``;
    when it is not supplied the current year is used.
    """
    if not text:
        return ParsedDate(value=None, precision="unknown", raw_text="")

    match = ISO_RE.search(text)
    if match:
        try:
            value = date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
            return ParsedDate(value=value, precision="exact", raw_text=match.group(0))
        except ValueError:
            pass

    match = DAY_FIRST_RE.search(text)
    if match:
        month = _month_number(match.group("month"))
        if month:
            try:
                value = date(int(match.group("year")), month, int(match.group("day")))
                return ParsedDate(value=value, precision="exact", raw_text=match.group(0))
            except ValueError:
                pass

    match = MONTH_FIRST_RE.search(text)
    if match:
        month = _month_number(match.group("month"))
        if month:
            try:
                value = date(int(match.group("year")), month, int(match.group("day")))
                return ParsedDate(value=value, precision="exact", raw_text=match.group(0))
            except ValueError:
                pass

    match = NUMERIC_RE.search(text)
    if match:
        year = int(match.group("year"))
        if year < 100:
            year += 2000
        month = int(match.group("month"))
        day = int(match.group("day"))
        precision = "exact"
        if day == 1 and month in (1,):
            precision = "month"
        try:
            value = date(year, month, day)
        except ValueError:
            value = date(year, month, 1)
            precision = "month"
        return ParsedDate(value=value, precision=precision, raw_text=match.group(0))

    match = MONTH_YEAR_RE.search(text)
    if match:
        month = _month_number(match.group("month"))
        if month:
            year = int(match.group("year"))
            return ParsedDate(value=date(year, month, 1), precision="month", raw_text=match.group(0))

    year_only = re.search(r"\b(20\d{2})\b", text)
    if year_only:
        return ParsedDate(value=date(int(year_only.group(1)), 1, 1), precision="year", raw_text=year_only.group(0))

    return ParsedDate(value=None, precision="unknown", raw_text=text.strip()[:120])


def parse_datetime(text: str, *, timezone_name: str | None = None) -> ParsedDate:
    """Parse a date, also detecting a stated clock time (e.g. "17:00 GMT")."""
    parsed = parse_date(text)
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(?:\s*([A-Z]{2,5}))?", text)
    if time_match and parsed.value:
        tz = time_match.group(3) or timezone_name
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        try:
            moment = datetime(
                parsed.value.year,
                parsed.value.month,
                parsed.value.day,
                hour,
                minute,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return parsed
        return ParsedDate(
            value=moment,
            precision="exact",
            raw_text=f"{parsed.raw_text} {time_match.group(0)}".strip(),
            timezone=tz,
            is_datetime=True,
        )
    return parsed


def deadline_is_open(deadline: date | datetime | None, *, now: datetime | None = None) -> bool | None:
    """Whether a deadline is still in the future.

    Returns ``None`` when the deadline is unknown — the caller must not treat
    "unknown" as "open".
    """
    if deadline is None:
        return None
    reference = now or datetime.now(timezone.utc)
    if isinstance(deadline, datetime):
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline > reference
    return deadline >= reference.date()


def cycle_status(deadline: date | datetime | None, opens_at: date | None, *, now: datetime | None = None) -> str:
    """Derive the cycle status from dates.

    A cycle with an unknown deadline is ``undetermined``, never ``open``: the
    platform refuses to claim a cycle is open when it cannot see the deadline.
    """
    reference = now or datetime.now(timezone.utc)
    today = reference.date()

    if opens_at and opens_at > today:
        return "upcoming"
    if deadline is None:
        return "undetermined"
    if isinstance(deadline, datetime):
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return "open" if deadline >= reference else "closed"
    return "open" if deadline >= today else "closed"


def days_until(deadline: date | datetime | None, *, now: datetime | None = None) -> int | None:
    """Whole days until a deadline (negative once it has passed)."""
    if deadline is None:
        return None
    reference = now or datetime.now(timezone.utc)
    if isinstance(deadline, datetime):
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return (deadline.date() - reference.date()).days
    return (deadline - reference.date()).days
