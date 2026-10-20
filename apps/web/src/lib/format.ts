/**
 * Formatting helpers shared across surfaces.
 *
 * Rules:
 *  - a missing fact is rendered as an explicit "not stated" marker, never as
 *    `Invalid Date` or a blank cell;
 *  - deadlines always carry both an absolute date and a relative hint, because a
 *    relative hint alone hides precision;
 *  - nothing here ever renders a percentage as a probability of success.
 */

export const NOT_STATED = 'Not stated';

export type DeadlineTone = 'unknown' | 'past' | 'urgent' | 'soon' | 'open';

export interface RelativeDeadline {
  /** Human readable relative hint, e.g. "closes in 12 days". */
  label: string;
  /** Whole days until the deadline; negative when the deadline has passed. */
  days: number | null;
  tone: DeadlineTone;
  /** True when the deadline is known and in the future. */
  isOpen: boolean;
}

function toDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** `2027-03-01` → `1 Mar 2027`. */
export function formatDate(value: string | null | undefined): string {
  const date = toDate(value);
  if (!date) return NOT_STATED;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(date);
}

/** `2027-03-01T09:00:00Z` → `1 Mar 2027, 09:00 UTC`. */
export function formatDateTime(value: string | null | undefined): string {
  const date = toDate(value);
  if (!date) return NOT_STATED;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short',
  }).format(date);
}

/** ISO timestamp → `1 Mar 2027` (date only). */
export function formatSnapshotDate(value: string | null | undefined): string {
  return formatDate(value);
}

/** `150000` + `NGN` → `NGN 150,000`. */
export function formatCurrency(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return NOT_STATED;
  const code = currency ?? '';
  const formatted = new Intl.NumberFormat('en-GB', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(amount);
  return code ? `${code} ${formatted}` : formatted;
}

/** Whole days between `now` and `value`; `null` when the date is unknown. */
export function daysUntil(value: string | null | undefined, now: Date = new Date()): number | null {
  const date = toDate(value);
  if (!date) return null;
  const msPerDay = 1000 * 60 * 60 * 24;
  return Math.ceil((date.getTime() - now.getTime()) / msPerDay);
}

/**
 * "closes in 12 days" / "closes tomorrow" / "closed 3 days ago" /
 * "deadline not stated".
 */
export function formatRelativeDeadline(
  value: string | null | undefined,
  now: Date = new Date(),
): RelativeDeadline {
  const days = daysUntil(value, now);
  if (days === null) {
    return { label: 'Deadline not stated', days: null, tone: 'unknown', isOpen: false };
  }
  if (days < 0) {
    const past = Math.abs(days);
    return {
      label: `closed ${past} day${past === 1 ? '' : 's'} ago`,
      days,
      tone: 'past',
      isOpen: false,
    };
  }
  if (days === 0) {
    return { label: 'closes today', days, tone: 'urgent', isOpen: true };
  }
  if (days === 1) {
    return { label: 'closes tomorrow', days, tone: 'urgent', isOpen: true };
  }
  if (days <= 14) {
    return { label: `closes in ${days} days`, days, tone: 'urgent', isOpen: true };
  }
  if (days <= 45) {
    return { label: `closes in ${days} days`, days, tone: 'soon', isOpen: true };
  }
  return { label: `closes in ${days} days`, days, tone: 'open', isOpen: true };
}

/** `closes in 12 days` with an absolute date appended. */
export function formatDeadlinePair(value: string | null | undefined, now: Date = new Date()): string {
  const relative = formatRelativeDeadline(value, now);
  const absolute = formatDate(value);
  if (relative.days === null) return relative.label;
  return `${absolute} (${relative.label})`;
}

/** Percentage as a plain share, e.g. `0.75` → `75%`. Never a probability of success. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_STATED;
  return `${Math.round(value * 100)}%`;
}

/** Human-readable representation of an arbitrary JSON value. */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return NOT_STATED;
  if (typeof value === 'string') return value.length > 0 ? value : NOT_STATED;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return value.length === 0 ? NOT_STATED : value.map((entry) => formatValue(entry)).join(', ');
  }
  try {
    return JSON.stringify(value);
  } catch {
    return NOT_STATED;
  }
}

/** `gpa.min_overall` → `Gpa min overall` — used for missing-field prompts. */
export function humaniseField(field: string): string {
  const tail = field.includes('.') ? field.slice(field.indexOf('.') + 1) : field;
  const spaced = tail.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** `Second Class Upper` style labels for degree levels and comparators. */
export function humaniseToken(token: string): string {
  return token
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^./, (character) => character.toUpperCase());
}
