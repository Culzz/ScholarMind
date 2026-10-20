import { ClaimChip } from '@/components/ClaimChip';
import { Table, type TableColumn } from '@/components/ui/Table';
import { formatCurrency } from '@/lib/format';
import type { CoverageStatus, FundingComponent, FundingComponentKind } from '@/types/api';

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

const COVERAGE_TONE: Record<CoverageStatus, 'emerald' | 'zinc' | 'amber' | 'slate'> = {
  included: 'emerald',
  excluded: 'zinc',
  conditional: 'amber',
  unknown: 'slate',
};

export interface FundingBreakdownProps {
  components: FundingComponent[];
  caption?: string;
}

/**
 * Funding is always shown component by component — never as one "fully funded"
 * boolean (SRS FR-2.2).
 */
export function FundingBreakdown({
  components,
  caption = 'Funding components',
}: FundingBreakdownProps): JSX.Element {
  const columns: TableColumn<FundingComponent>[] = [
    {
      key: 'component',
      header: 'Component',
      render: (row) => <span className="font-medium text-slate-900">{COMPONENT_LABEL[row.component]}</span>,
    },
    {
      key: 'coverage',
      header: 'Coverage',
      render: (row) => (
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
            COVERAGE_TONE[row.coverage_status] === 'emerald'
              ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
              : COVERAGE_TONE[row.coverage_status] === 'zinc'
                ? 'border-zinc-300 bg-zinc-100 text-zinc-700'
                : COVERAGE_TONE[row.coverage_status] === 'amber'
                  ? 'border-amber-300 bg-amber-50 text-amber-900'
                  : 'border-slate-300 bg-slate-100 text-slate-700'
          }`}
        >
          {COVERAGE_LABEL[row.coverage_status]}
        </span>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      render: (row) => formatCurrency(row.amount, row.currency),
    },
    {
      key: 'period',
      header: 'Period',
      render: (row) => (row.amount_period === 'unknown' ? 'Not stated' : row.amount_period.replace('_', ' ')),
    },
    {
      key: 'conditions',
      header: 'Conditions',
      render: (row) => row.conditions ?? 'None stated',
    },
    {
      key: 'state',
      header: 'Evidence state',
      render: (row) => <ClaimChip state={row.claim_state} size="sm" />,
    },
  ];

  return (
    <Table
      caption={caption}
      columns={columns}
      rows={components}
      rowKey={(row) => row.id}
      emptyMessage="No funding components are recorded for this cycle yet."
    />
  );
}

export default FundingBreakdown;
