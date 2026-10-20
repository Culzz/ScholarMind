import { ClaimChip } from '@/components/ClaimChip';
import { DeadlinePill } from '@/components/DeadlinePill';
import { Badge } from '@/components/ui/Badge';
import { formatDateTime } from '@/lib/format';
import type { ScholarshipListItem } from '@/types/api';
import { Link } from 'react-router-dom';

export interface ScholarshipCardProps {
  scholarship: ScholarshipListItem;
}

const STATUS_LABEL: Record<string, string | undefined> = {
  open: 'Open',
  upcoming: 'Upcoming',
  closed: 'Closed',
  undetermined: 'Status not established',
};

/**
 * FR-1.4: every card shows the official link, the deadline, the cycle and the
 * source check time. The deadline carries its claim state as text.
 */
export function ScholarshipCard({ scholarship }: ScholarshipCardProps): JSX.Element {
  const cycle = scholarship.current_cycle ?? null;
  const officialUrl = scholarship.official_url ?? scholarship.website_url ?? null;

  return (
    <article className="flex h-full flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-slate-900">
            <Link
              to={`/scholarships/${scholarship.id}`}
              className="rounded underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
            >
              {scholarship.name}
            </Link>
          </h3>
          <p className="mt-0.5 text-sm text-slate-600">
            {scholarship.provider_name}
            {scholarship.provider_country_iso3 ? ` · ${scholarship.provider_country_iso3}` : ''}
          </p>
        </div>
        {cycle ? (
          <Badge tone={cycle.status === 'open' ? 'emerald' : cycle.status === 'closed' ? 'zinc' : 'amber'}>
            {STATUS_LABEL[cycle.status] ?? cycle.status}
          </Badge>
        ) : null}
      </div>

      {scholarship.description ? (
        <p className="mt-2 line-clamp-3 text-sm text-slate-700">{scholarship.description}</p>
      ) : null}

      <dl className="mt-3 grid grid-cols-1 gap-1 text-xs text-slate-600 sm:grid-cols-2">
        <div>
          <dt className="inline font-medium text-slate-700">Cycle: </dt>
          <dd className="inline">{cycle ? cycle.cycle_label : 'No cycle published'}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-slate-700">Source checked: </dt>
          <dd className="inline">{formatDateTime(scholarship.source_last_checked_at ?? null)}</dd>
        </div>
      </dl>

      <div className="mt-3">
        {cycle ? (
          <DeadlinePill
            deadline={cycle.deadline_at}
            claimState={cycle.claim_state}
            rawText={cycle.deadline_raw_text}
            timezone={cycle.deadline_timezone}
          />
        ) : (
          <p className="text-xs text-slate-600">No deadline has been published for this cycle.</p>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {scholarship.deadline_claim_state ? (
          <ClaimChip state={scholarship.deadline_claim_state} size="sm" />
        ) : null}
        {scholarship.study_levels.map((level) => (
          <Badge key={level} tone="sky">
            {level.replace('_', ' ')}
          </Badge>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 pt-1">
        <Link
          to={`/scholarships/${scholarship.id}`}
          className="inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
        >
          View evidence
        </Link>
        {officialUrl ? (
          <a
            href={officialUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
          >
            Official site
            <span className="sr-only"> for {scholarship.name} (opens in a new tab)</span>
          </a>
        ) : (
          <span className="text-xs text-slate-600">No official link recorded yet.</span>
        )}
      </div>
    </article>
  );
}

export default ScholarshipCard;
