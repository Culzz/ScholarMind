import { ClaimChip } from '@/components/ClaimChip';
import { EvidenceSnippet } from '@/components/EvidenceSnippet';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatDateTime, formatValue } from '@/lib/format';
import type { Conflict, EvidenceClaim, FreshnessWarning } from '@/types/api';

export interface EvidencePanelProps {
  evidence: EvidenceClaim[];
  conflicts: Conflict[];
  freshnessWarnings: FreshnessWarning[];
}

/**
 * FR-5.4 / FR-6.5: cited excerpts with their snapshot time, freshness warnings
 * and a conflict banner. When two official sources disagree, both values are
 * shown and neither is asserted as final.
 */
export function EvidencePanel({
  evidence,
  conflicts,
  freshnessWarnings,
}: EvidencePanelProps): JSX.Element {
  return (
    <div className="space-y-4">
      {conflicts.length > 0 ? (
        <div
          role="status"
          className="rounded-md border-2 border-rose-400 bg-rose-50 px-3 py-3 text-sm text-rose-900"
        >
          <p className="font-semibold">
            Conflicting sources — {conflicts.length} field{conflicts.length === 1 ? '' : 's'} in dispute
          </p>
          <p className="mt-1 text-rose-800">
            Both values are shown below. We do not assert a single deadline or amount while official
            sources disagree.
          </p>
          <ul className="mt-2 space-y-2">
            {conflicts.map((conflict) => (
              <li key={conflict.id} className="rounded border border-rose-200 bg-white px-2.5 py-2">
                <p className="font-medium">{conflict.field_name.replace(/_/g, ' ')}</p>
                <div className="mt-1 grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                      Source {conflict.source_name_a ?? 'A'}
                    </p>
                    <p className="text-sm text-slate-800">{formatValue(conflict.value_a)}</p>
                    {conflict.snapshot_at_a ? (
                      <p className="text-xs text-slate-600">Snapshot {formatDateTime(conflict.snapshot_at_a)}</p>
                    ) : null}
                    {conflict.source_url_a ? (
                      <a
                        href={conflict.source_url_a}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-xs font-medium text-sky-700 underline underline-offset-2"
                      >
                        Open source
                      </a>
                    ) : null}
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                      Source {conflict.source_name_b ?? 'B'}
                    </p>
                    <p className="text-sm text-slate-800">{formatValue(conflict.value_b)}</p>
                    {conflict.snapshot_at_b ? (
                      <p className="text-xs text-slate-600">Snapshot {formatDateTime(conflict.snapshot_at_b)}</p>
                    ) : null}
                    {conflict.source_url_b ? (
                      <a
                        href={conflict.source_url_b}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-xs font-medium text-sky-700 underline underline-offset-2"
                      >
                        Open source
                      </a>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {freshnessWarnings.length > 0 ? (
        <Card title="Freshness warnings">
          <ul className="space-y-2">
            {freshnessWarnings.map((warning, index) => (
              <li key={`${warning.message}-${index}`} className="flex flex-wrap items-start gap-2">
                <ClaimChip state={warning.claim_state} size="sm" />
                <div>
                  <p className="text-sm text-slate-800">{warning.message}</p>
                  {warning.last_checked_at ? (
                    <p className="text-xs text-slate-600">
                      Last checked {formatDateTime(warning.last_checked_at)}
                      {warning.source_name ? ` · ${warning.source_name}` : ''}
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card title="Cited excerpts" description="Each excerpt shows the snapshot it was taken from.">
        {evidence.length === 0 ? (
          <EmptyState
            title="No excerpts were cited"
            description="An answer without retrievable excerpts is not a grounded answer."
          />
        ) : (
          <ul className="space-y-3">
            {evidence.map((item, index) => (
              <li key={item.id}>
                <EvidenceSnippet evidence={item} index={index} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export default EvidencePanel;
