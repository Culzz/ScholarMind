import type { ReactNode } from 'react';

import { ClaimChip } from '@/components/ClaimChip';
import { DeadlinePill } from '@/components/DeadlinePill';
import { VERDICT_CLASSES, VERDICT_LABEL } from '@/components/EligibilityRow';
import { formatValue } from '@/lib/format';
import type {
  CompareItem,
  CompareResponse,
  CoverageStatus,
  FundingComponentKind,
} from '@/types/api';

const COMPONENT_ORDER: FundingComponentKind[] = [
  'tuition',
  'stipend',
  'travel',
  'accommodation',
  'insurance',
  'equipment',
  'research',
  'other',
];

const COMPONENT_LABEL: Record<FundingComponentKind, string> = {
  tuition: 'Tuition',
  stipend: 'Stipend',
  travel: 'Travel',
  accommodation: 'Accommodation',
  insurance: 'Insurance',
  equipment: 'Equipment',
  research: 'Research costs',
  other: 'Other',
};

const COVERAGE_LABEL: Record<CoverageStatus, string> = {
  included: 'Included',
  excluded: 'Not covered',
  conditional: 'Conditional',
  unknown: 'Not established',
};

const COVERAGE_CLASSES: Record<CoverageStatus, string> = {
  included: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  excluded: 'border-zinc-300 bg-zinc-100 text-zinc-700',
  conditional: 'border-amber-300 bg-amber-50 text-amber-900',
  unknown: 'border-slate-300 bg-slate-100 text-slate-700',
};

export interface CompareMatrixProps {
  comparison: CompareResponse;
}

function Cell({ children }: { children: ReactNode }): JSX.Element {
  return <div className="px-3 py-3 align-top text-sm text-slate-700">{children}</div>;
}

/**
 * FR-7.2: rule-level verdicts, funding components, deadline status, unknown
 * conditions, source freshness and unresolved conflicts.
 */
export function CompareMatrix({ comparison }: CompareMatrixProps): JSX.Element {
  const items = comparison.items;

  if (items.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
        Nothing to compare yet.
      </p>
    );
  }

  const gridTemplate = { gridTemplateColumns: `160px repeat(${items.length}, minmax(180px, 1fr))` };

  const rows: Array<{ label: string; render: (item: CompareItem) => ReactNode }> = [
    {
      label: 'Deadline',
      render: (item) =>
        item.cycle ? (
          <DeadlinePill
            deadline={item.cycle.deadline_at}
            claimState={item.cycle.claim_state}
            rawText={item.cycle.deadline_raw_text}
            timezone={item.cycle.deadline_timezone}
          />
        ) : (
          <span className="text-slate-600">No cycle published</span>
        ),
    },
    {
      label: 'Cycle',
      render: (item) => (
        <span>
          {item.cycle ? item.cycle.cycle_label : 'Not stated'}
          {item.cycle ? (
            <span className="mt-1 block text-xs text-slate-600">
              Intake year {item.cycle.intake_year}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      label: 'Requirements met',
      render: (item) => {
        const satisfied = item.rule_verdicts.filter((verdict) => verdict.verdict === 'satisfied').length;
        const unknown = item.rule_verdicts.filter((verdict) => verdict.verdict === 'unknown').length;
        const failed = item.rule_verdicts.filter((verdict) => verdict.verdict === 'not_satisfied').length;
        return (
          <span className="text-sm text-slate-700">
            {satisfied} met, {failed} not met, {unknown} unknown
          </span>
        );
      },
    },
    {
      label: 'Rule verdicts',
      render: (item) =>
        item.rule_verdicts.length === 0 ? (
          <span className="text-slate-600">No verdicts available</span>
        ) : (
          <ul className="space-y-1.5">
            {item.rule_verdicts.map((verdict) => (
              <li key={verdict.rule_id}>
                <span
                  className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${VERDICT_CLASSES[verdict.verdict]}`}
                >
                  {VERDICT_LABEL[verdict.verdict]}
                </span>
                <span className="mt-0.5 block text-xs text-slate-700">{verdict.rule_text}</span>
              </li>
            ))}
          </ul>
        ),
    },
    ...COMPONENT_ORDER.map((component) => ({
      label: COMPONENT_LABEL[component],
      render: (item: CompareItem) => {
        const funding = item.funding.find((entry) => entry.component === component);
        if (!funding) {
          return <span className="text-slate-600">Not stated</span>;
        }
        return (
          <span className="flex flex-col items-start gap-1">
            <span
              className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${COVERAGE_CLASSES[funding.coverage_status]}`}
            >
              {COVERAGE_LABEL[funding.coverage_status]}
            </span>
            {funding.amount !== null ? (
              <span className="text-xs text-slate-600">{formatValue(funding.amount)} {funding.currency ?? ''}</span>
            ) : null}
          </span>
        );
      },
    })),
    {
      label: 'Unknown conditions',
      render: (item) =>
        item.unknown_conditions.length === 0 ? (
          <span className="text-slate-600">None recorded</span>
        ) : (
          <ul className="list-disc pl-5 text-xs text-slate-700">
            {item.unknown_conditions.map((condition) => (
              <li key={condition}>{condition}</li>
            ))}
          </ul>
        ),
    },
    {
      label: 'Source freshness',
      render: (item) =>
        item.source_freshness.length === 0 ? (
          <span className="text-slate-600">Not recorded</span>
        ) : (
          <ul className="space-y-1">
            {item.source_freshness.map((source) => (
              <li key={source.source_id} className="flex items-center gap-1.5">
                <ClaimChip state={source.claim_state} size="sm" />
                <span className="text-xs text-slate-600">{source.source_name ?? 'Source'}</span>
              </li>
            ))}
          </ul>
        ),
    },
  ];

  return (
    <div className="space-y-4">
      {comparison.conflicts.length > 0 ? (
        <div role="status" className="rounded-md border border-rose-300 bg-rose-50 px-3 py-3 text-sm text-rose-900">
          <p className="font-semibold">
            {comparison.conflicts.length} unresolved conflict
            {comparison.conflicts.length === 1 ? '' : 's'} across the compared records
          </p>
          <ul className="mt-1 list-disc pl-5">
            {comparison.conflicts.map((conflict) => (
              <li key={conflict.id}>
                {conflict.field_name.replace(/_/g, ' ')}: {formatValue(conflict.value_a)} vs{' '}
                {formatValue(conflict.value_b)} — neither value is asserted as final.
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <div className="min-w-full">
          <div
            className="grid border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
            style={gridTemplate}
          >
            <div className="px-3 py-2">Criterion</div>
            {items.map((item) => (
              <div key={item.scholarship.id} className="px-3 py-2">
                {item.scholarship.name}
                <span className="mt-0.5 block text-xs font-normal normal-case text-slate-600">
                  {item.scholarship.provider_name}
                </span>
              </div>
            ))}
          </div>

          {rows.map((row) => (
            <div
              key={row.label}
              className="grid border-b border-slate-100 last:border-b-0"
              style={gridTemplate}
            >
              <div className="bg-slate-50/60 px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-600">
                {row.label}
              </div>
              {items.map((item) => (
                <Cell key={item.scholarship.id}>{row.render(item)}</Cell>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default CompareMatrix;
