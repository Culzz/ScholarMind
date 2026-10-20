import { describe, expect, it } from 'vitest';

import {
  formatCurrency,
  formatDate,
  formatRelativeDeadline,
  humaniseField,
  NOT_STATED,
} from '@/lib/format';

describe('format helpers', () => {
  it('renders an explicit marker for missing facts', () => {
    expect(formatDate(null)).toBe(NOT_STATED);
    expect(formatDate('not-a-date')).toBe(NOT_STATED);
    expect(formatCurrency(null, 'NGN')).toBe(NOT_STATED);
  });

  it('formats currency with its code', () => {
    expect(formatCurrency(150000, 'NGN')).toContain('NGN');
  });

  it('describes deadlines relatively', () => {
    const now = new Date('2026-10-20T00:00:00Z');
    expect(formatRelativeDeadline('2026-10-21T00:00:00Z', now).label).toBe('closes tomorrow');
    expect(formatRelativeDeadline('2026-10-20T00:00:00Z', now).label).toBe('closes today');
    expect(formatRelativeDeadline('2026-11-01T00:00:00Z', now).label).toBe('closes in 12 days');
    expect(formatRelativeDeadline('2026-10-01T00:00:00Z', now).tone).toBe('past');
    expect(formatRelativeDeadline(null, now).tone).toBe('unknown');
  });

  it('humanises profile field names', () => {
    expect(humaniseField('gpa.min_overall')).toBe('Min overall');
    expect(humaniseField('age')).toBe('Age');
  });
});
