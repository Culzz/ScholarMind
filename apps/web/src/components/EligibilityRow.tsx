import { Badge } from '@/components/ui/Badge';
import { formatValue, humaniseField } from '@/lib/format';
import type { AssessmentResult, Verdict } from '@/types/api';

export const VERDICT_LABEL: Record<Verdict, string> = {
  satisfied: 'Requirement met',
  not_satisfied: 'Requirement not met',
  unknown: 'Not enough information',
  needs_review: 'Needs review',
};

export const VERDICT_CLASSES: Record<Verdict, string> = {
  satisfied: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  not_satisfied: 'border-rose-300 bg-rose-50 text-rose-900',
  unknown: 'border-amber-300 bg-amber-50 text-amber-900',
  needs_review: 'border-slate-400 bg-slate-100 text-slate-900',
};

export interface EligibilityRowProps {
  result: AssessmentResult;
  /** Evidence ids resolved to short descriptions, when available. */
  evidenceLookup?: Record<string, { label: string; url?: string | null }>;
}

/**
 * One eligibility rule with its verdict, the reason, the evidence behind it and
 * a prompt for the profile field that is still missing. A rule is never reduced
 * to a score.
 */
export function EligibilityRow({ result, evidenceLookup }: EligibilityRowProps): JSX.Element {
  const fact = formatValue(result.profile_fact);
  const evidence = (result.evidence_ids ?? [])
    .map((id) => evidenceLookup?.[id])
    .filter((entry): entry is { label: string; url?: string | null } => Boolean(entry));

  return (
    <li className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm font-medium text-slate-900">{result.rule_text}</p>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${VERDICT_CLASSES[result.verdict]}`}
        >
          {VERDICT_LABEL[result.verdict]}
        </span>
      </div>

      <p className="mt-2 text-sm text-slate-700">{result.reason}</p>

      <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-600">
        <div>
          <dt className="inline font-medium text-slate-700">Your fact: </dt>
          <dd className="inline">{fact}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-slate-700">Requirement type: </dt>
          <dd className="inline">{result.comparability}</dd>
        </div>
      </dl>

      {result.verdict === 'unknown' && result.missing_field ? (
        <p className="mt-2 rounded border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
          Still missing: <strong>{humaniseField(result.missing_field)}</strong>. Add it to your profile to
          resolve this requirement — we will not guess.
        </p>
      ) : null}

      {result.verdict === 'needs_review' ? (
        <p className="mt-2 rounded border border-slate-300 bg-slate-100 px-2.5 py-1.5 text-xs text-slate-800">
          This requirement could not be applied automatically — the source wording is ambiguous or two
          official sources disagree. Confirm with the scholarship office.
        </p>
      ) : null}

      {evidence.length > 0 ? (
        <div className="mt-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-600">Evidence</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {evidence.map((entry) => (
              <li key={entry.label}>
                {entry.url ? (
                  <a
                    href={entry.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center rounded-full border border-sky-300 bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-800 hover:bg-sky-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
                  >
                    {entry.label}
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                ) : (
                  <Badge tone="sky">{entry.label}</Badge>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </li>
  );
}

export default EligibilityRow;
