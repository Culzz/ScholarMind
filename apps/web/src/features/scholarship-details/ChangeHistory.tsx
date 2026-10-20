import { ClaimChip } from '@/components/ClaimChip';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatDateTime, formatValue } from '@/lib/format';
import type { ChangeEvent, ChangeSeverity } from '@/types/api';

export interface ChangeHistoryProps {
  changes: ChangeEvent[];
}

const SEVERITY_LABEL: Record<ChangeSeverity, string> = {
  informational: 'Informational',
  important: 'Important',
  critical: 'Critical',
};

const SEVERITY_TONE: Record<ChangeSeverity, 'neutral' | 'amber' | 'rose'> = {
  informational: 'neutral',
  important: 'amber',
  critical: 'rose',
};

const REVIEW_LABEL: Record<string, string | undefined> = {
  pending: 'Awaiting review',
  approved: 'Approved',
  rejected: 'Rejected',
  auto_accepted: 'Auto-accepted (high confidence)',
};

const REVIEW_TONE: Record<string, 'neutral' | 'emerald' | 'zinc' | undefined> = {
  pending: 'neutral',
  approved: 'emerald',
  rejected: 'zinc',
  auto_accepted: 'emerald',
};

/**
 * FR-2.4 / FR-4: the timeline of detected changes — old value, new value,
 * detection time and review status.
 */
export function ChangeHistory({ changes }: ChangeHistoryProps): JSX.Element {
  if (changes.length === 0) {
    return (
      <EmptyState
        title="No changes detected yet"
        description="When the source page changes, the difference is recorded here with its detection time and review status."
      />
    );
  }

  return (
    <ol className="space-y-3">
      {changes.map((change) => (
        <li key={change.id} className="rounded-md border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-slate-900">
              {change.change_type.replace('_', ' ')} · {change.field_name.replace(/_/g, ' ')}
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone={SEVERITY_TONE[change.severity]}>{SEVERITY_LABEL[change.severity]}</Badge>
              <Badge tone={REVIEW_TONE[change.review_status] ?? 'neutral'}>
                {REVIEW_LABEL[change.review_status] ?? change.review_status}
              </Badge>
            </div>
          </div>

          <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
            <div className="rounded border border-slate-200 bg-slate-50 px-2.5 py-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Before</p>
              <p className="text-slate-800">{formatValue(change.old_value)}</p>
            </div>
            <div className="rounded border border-emerald-200 bg-emerald-50 px-2.5 py-2">
              <p className="text-xs font-medium uppercase tracking-wide text-emerald-700">After</p>
              <p className="text-emerald-900">{formatValue(change.new_value)}</p>
            </div>
          </div>

          <p className="mt-2 text-xs text-slate-600">
            Detected {formatDateTime(change.detected_at)}
            {change.source_name ? ` · Source: ${change.source_name}` : ''}
          </p>
          {change.review_note ? (
            <p className="mt-1 text-xs text-slate-700">Reviewer note: {change.review_note}</p>
          ) : null}
          {change.review_status === 'pending' ? (
            <p className="mt-2">
              <ClaimChip state="needs_verification" size="sm" label="Pending review — not yet a confirmed fact" />
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export default ChangeHistory;
