import { Badge } from '@/components/ui/Badge';
import { ClaimChip } from '@/components/ClaimChip';
import { formatDateTime } from '@/lib/format';
import type { ClaimState, SourceDocument, TrustTier } from '@/types/api';

const TRUST_TIER_LABEL: Record<TrustTier, string> = {
  official_primary: 'Official — primary funder',
  official_secondary: 'Official — secondary',
  partner: 'Partner',
  aggregator: 'Aggregator',
};

const TRUST_TIER_TONE: Record<TrustTier, 'emerald' | 'sky' | 'violet' | 'neutral'> = {
  official_primary: 'emerald',
  official_secondary: 'sky',
  partner: 'violet',
  aggregator: 'neutral',
};

export interface SourceCardProps {
  source: Pick<
    SourceDocument,
    | 'id'
    | 'url'
    | 'trust_tier'
    | 'last_checked_at'
    | 'last_success_at'
    | 'fetch_status'
    | 'fetch_error'
    | 'claim_state'
  > & { name?: string | null };
  /** Optional override for the display name. */
  name?: string | null;
}

/**
 * A source card: official name, trust tier, last check time and the link to the
 * official page. The claim state of the source is shown as text as well.
 */
export function SourceCard({ source, name }: SourceCardProps): JSX.Element {
  const displayName = name ?? source.name ?? source.url;
  const checkedAt = source.last_checked_at ?? source.last_success_at ?? null;

  return (
    <article className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">{displayName}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2">
            <Badge tone={TRUST_TIER_TONE[source.trust_tier]}>{TRUST_TIER_LABEL[source.trust_tier]}</Badge>
            <ClaimChip state={source.claim_state as ClaimState} size="sm" />
          </p>
        </div>
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer noopener"
          className="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-sky-700 hover:bg-sky-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
        >
          Official page
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-1 text-xs text-slate-600 sm:grid-cols-2">
        <div>
          <dt className="inline font-medium text-slate-700">Last checked: </dt>
          <dd className="inline">{formatDateTime(checkedAt)}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-slate-700">Fetch status: </dt>
          <dd className="inline">{source.fetch_status}</dd>
        </div>
      </dl>
      {source.fetch_error ? (
        <p className="mt-2 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-900">
          Last fetch failed: {source.fetch_error}. The value below may be out of date.
        </p>
      ) : null}
    </article>
  );
}

export default SourceCard;
