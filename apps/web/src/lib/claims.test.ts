import { describe, expect, it } from 'vitest';

import {
  CLAIM_STATE_META,
  CLAIM_STATES,
  claimStateMeta,
  fromFetchStatus,
  fromValidationStatus,
  isUnconfirmed,
} from '@/lib/claims';

describe('claim-state registry', () => {
  it('exposes exactly the five user-facing claim states', () => {
    expect([...CLAIM_STATES]).toEqual([
      'confirmed',
      'not_established',
      'needs_verification',
      'stale',
      'expired',
    ]);
  });

  it('gives every state a text label and its own colours', () => {
    for (const state of CLAIM_STATES) {
      const meta = CLAIM_STATE_META[state];
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.chipClass.length).toBeGreaterThan(0);
      expect(meta.description.length).toBeGreaterThan(0);
    }
    const chipClasses = CLAIM_STATES.map((state) => CLAIM_STATE_META[state].chipClass);
    expect(new Set(chipClasses).size).toBe(CLAIM_STATES.length);
  });

  it('falls back to "not established" for unknown states', () => {
    const meta = claimStateMeta('something-else');
    expect(meta).toBe(CLAIM_STATE_META.not_established);
  });

  it('never maps an unresolved validation status to confirmed', () => {
    expect(fromValidationStatus('confirmed')).toBe('confirmed');
    expect(fromValidationStatus('conflicting')).toBe('needs_verification');
    expect(fromValidationStatus('stale')).toBe('stale');
    expect(fromValidationStatus('ambiguous')).toBe('not_established');
    expect(fromValidationStatus('unresolved')).toBe('not_established');
    expect(fromValidationStatus('rejected')).toBe('not_established');
    expect(fromValidationStatus(undefined)).toBe('not_established');
  });

  it('treats a failed fetch as stale, not as confirmed', () => {
    expect(fromFetchStatus('ok')).toBe('confirmed');
    expect(fromFetchStatus('error')).toBe('stale');
    expect(fromFetchStatus('blocked')).toBe('stale');
    expect(fromFetchStatus('not_found')).toBe('stale');
  });

  it('reports unconfirmed states', () => {
    expect(isUnconfirmed('confirmed')).toBe(false);
    expect(isUnconfirmed('stale')).toBe(true);
  });
});
