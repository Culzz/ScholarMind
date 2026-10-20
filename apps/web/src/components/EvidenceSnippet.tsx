import { ClaimChip } from '@/components/ClaimChip';
import { fromValidationStatus } from '@/lib/claims';
import { formatDateTime } from '@/lib/format';
import type { EvidenceClaim } from '@/types/api';

export interface EvidenceSnippetProps {
  evidence: EvidenceClaim;
  /** Optional index used in the accessible label, e.g. "Excerpt 2". */
  index?: number;
}

/**
 * A cited excerpt: the verbatim text, the snapshot it came from and the time
 * that snapshot was taken. The excerpt's own validation status is shown so a
 * reader can tell a confirmed quote from an unreviewed one.
 */
export function EvidenceSnippet({ evidence, index }: EvidenceSnippetProps): JSX.Element {
  const claimState = fromValidationStatus(evidence.validation_status);
  const excerpt = evidence.excerpt?.trim() || evidence.claim_text;

  return (
    <figure className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {index !== undefined ? `Excerpt ${index + 1}` : 'Excerpt'} · {evidence.claim_type}
        </span>
        <ClaimChip state={claimState} size="sm" />
      </figcaption>
      <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-sm italic text-slate-800">
        {excerpt}
      </blockquote>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
        <span>
          <span className="font-medium text-slate-700">Snapshot taken: </span>
          {formatDateTime(evidence.snapshot_at ?? null)}
        </span>
        {evidence.source_name ? (
          <span>
            <span className="font-medium text-slate-700">Source: </span>
            {evidence.source_name}
          </span>
        ) : null}
        <span className="font-mono text-[11px] text-slate-500">Evidence id: {evidence.id}</span>
      </div>
      {evidence.source_url ? (
        <a
          href={evidence.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-2 inline-block text-xs font-medium text-sky-700 underline underline-offset-2 hover:text-sky-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
        >
          Open the source page
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : null}
    </figure>
  );
}

export default EvidenceSnippet;
