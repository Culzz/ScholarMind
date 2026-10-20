/**
 * Claim-state registry — the single source of truth for how a fact's provenance
 * is presented in the UI.
 *
 * Rules encoded here (PLAN §11, SRS FR-5):
 *  - every material fact carries a visible claim state;
 *  - colour is never the only signal — each state has a text label that is always
 *    rendered next to the colour;
 *  - `confirmed` styling is only allowed when the source was checked inside the
 *    freshness policy.
 */
import type { ClaimState, EvidenceValidationStatus, FetchStatus } from '@/types/api';

export const CLAIM_STATES = [
  'confirmed',
  'not_established',
  'needs_verification',
  'stale',
  'expired',
] as const satisfies readonly ClaimState[];

export interface ClaimStateMeta {
  /** Human-readable label. Always rendered — colour never carries the meaning alone. */
  label: string;
  /** Short label for dense surfaces (tables, chips). */
  shortLabel: string;
  /** Tailwind classes for the chip background / border / text. */
  chipClass: string;
  /** Tailwind classes for a small status dot. */
  dotClass: string;
  /** Tailwind classes for the text colour alone. */
  textClass: string;
  /** Explanation shown in tooltips and panels. */
  description: string;
}

export const CLAIM_STATE_META: Record<ClaimState, ClaimStateMeta> = {
  confirmed: {
    label: 'Confirmed',
    shortLabel: 'Confirmed',
    chipClass:
      'bg-emerald-50 text-emerald-800 border border-emerald-300 ring-1 ring-inset ring-emerald-600/20',
    dotClass: 'bg-emerald-600',
    textClass: 'text-emerald-700',
    description:
      'An official source states this explicitly and the source was checked inside its freshness window.',
  },
  not_established: {
    label: 'Not established',
    shortLabel: 'Not established',
    chipClass: 'bg-amber-50 text-amber-900 border border-amber-300 ring-1 ring-inset ring-amber-600/20',
    dotClass: 'bg-amber-600',
    textClass: 'text-amber-700',
    description:
      'The reviewed material does not establish this fact. It may still exist but has not been found or confirmed.',
  },
  needs_verification: {
    label: 'Needs verification',
    shortLabel: 'Verify',
    chipClass: 'bg-rose-50 text-rose-900 border border-rose-300 ring-1 ring-inset ring-rose-600/20',
    dotClass: 'bg-rose-600',
    textClass: 'text-rose-700',
    description:
      'Two official sources disagree. Both values are shown; no single value is asserted as final.',
  },
  stale: {
    label: 'Stale',
    shortLabel: 'Stale',
    chipClass: 'bg-slate-100 text-slate-800 border border-slate-300 ring-1 ring-inset ring-slate-500/20',
    dotClass: 'bg-slate-500',
    textClass: 'text-slate-600',
    description:
      'The source could not be reached on the last check. The last known value is shown with its verification time.',
  },
  expired: {
    label: 'Expired',
    shortLabel: 'Expired',
    chipClass: 'bg-zinc-100 text-zinc-700 border border-zinc-300 ring-1 ring-inset ring-zinc-500/20',
    dotClass: 'bg-zinc-500',
    textClass: 'text-zinc-600',
    description: 'The cycle deadline has passed. Expired cycles are excluded from "open" by default.',
  },
};

/** Never fail a render because of an unexpected state string. */
export function claimStateMeta(state: ClaimState | string | null | undefined): ClaimStateMeta {
  if (state && (CLAIM_STATES as readonly string[]).includes(state)) {
    return CLAIM_STATE_META[state as ClaimState];
  }
  return CLAIM_STATE_META.not_established;
}

/**
 * Map a persisted `evidence_claims.validation_status` onto the user-facing
 * claim-state vocabulary. Anything we could not establish is `not_established`,
 * never `confirmed`.
 */
export function fromValidationStatus(status: EvidenceValidationStatus | string | null | undefined): ClaimState {
  switch (status) {
    case 'confirmed':
      return 'confirmed';
    case 'conflicting':
      return 'needs_verification';
    case 'stale':
      return 'stale';
    case 'ambiguous':
    case 'unresolved':
    case 'rejected':
      return 'not_established';
    default:
      return 'not_established';
  }
}

/** Derive the claim state of a source from its last fetch status. */
export function fromFetchStatus(status: FetchStatus | string | null | undefined): ClaimState {
  switch (status) {
    case 'ok':
      return 'confirmed';
    case 'error':
    case 'blocked':
    case 'not_found':
      return 'stale';
    default:
      return 'not_established';
  }
}

/** True when the state means "we cannot assert this". */
export function isUnconfirmed(state: ClaimState): boolean {
  return state !== 'confirmed';
}
