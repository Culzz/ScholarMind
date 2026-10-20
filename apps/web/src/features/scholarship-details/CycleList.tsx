import { Link } from 'react-router-dom';

import { ClaimChip } from '@/components/ClaimChip';
import { DeadlinePill } from '@/components/DeadlinePill';
import { Badge } from '@/components/ui/Badge';
import { Table, type TableColumn } from '@/components/ui/Table';
import { formatDate } from '@/lib/format';
import type { ScholarshipCycle } from '@/types/api';

export interface CycleListProps {
  cycles: ScholarshipCycle[];
  /** Id of the cycle to highlight as the active one. */
  currentCycleId?: string | null;
}

const STATUS_LABEL: Record<string, string | undefined> = {
  open: 'Open',
  upcoming: 'Upcoming',
  closed: 'Closed',
  undetermined: 'Status not established',
};

/**
 * FR-2.1: all known cycles with open date, deadline, status and rule count.
 */
export function CycleList({ cycles, currentCycleId }: CycleListProps): JSX.Element {
  const columns: TableColumn<ScholarshipCycle>[] = [
    {
      key: 'cycle',
      header: 'Cycle',
      render: (cycle) => (
        <div>
          <p className="font-medium text-slate-900">
            {cycle.cycle_label}
            {cycle.id === currentCycleId ? (
              <span className="ml-2 text-xs font-normal text-sky-700">current cycle</span>
            ) : null}
          </p>
          <p className="text-xs text-slate-600">Intake year {cycle.intake_year}</p>
        </div>
      ),
    },
    {
      key: 'opens',
      header: 'Opens',
      render: (cycle) => formatDate(cycle.opens_at),
    },
    {
      key: 'deadline',
      header: 'Deadline',
      render: (cycle) => (
        <DeadlinePill
          deadline={cycle.deadline_at}
          claimState={cycle.claim_state}
          rawText={cycle.deadline_raw_text}
          timezone={cycle.deadline_timezone}
        />
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (cycle) => (
        <div className="flex flex-col items-start gap-1">
          <Badge
            tone={
              cycle.status === 'open'
                ? 'emerald'
                : cycle.status === 'closed'
                  ? 'zinc'
                  : cycle.status === 'upcoming'
                    ? 'sky'
                    : 'amber'
            }
          >
            {STATUS_LABEL[cycle.status] ?? cycle.status}
          </Badge>
          <ClaimChip state={cycle.claim_state} size="sm" />
        </div>
      ),
    },
    {
      key: 'rules',
      header: 'Rules',
      render: (cycle) => (cycle.rule_count === undefined ? 'Not stated' : `${cycle.rule_count} rules`),
    },
  ];

  return (
    <Table
      caption="Scholarship cycles"
      columns={columns}
      rows={cycles}
      rowKey={(cycle) => cycle.id}
      emptyMessage="No cycles have been published for this scholarship yet."
    />
  );
}

export interface CycleListLinkProps {
  scholarshipId: string;
}

/** Small helper so other surfaces can deep-link to a cycle. */
export function CycleLink({ scholarshipId }: CycleListLinkProps): JSX.Element {
  return (
    <Link
      to={`/scholarships/${scholarshipId}`}
      className="rounded underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
    >
      View cycles
    </Link>
  );
}

export default CycleList;
