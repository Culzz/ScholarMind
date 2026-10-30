import type { ReactNode } from 'react';

import { ClaimChip } from '@/components/ClaimChip';
import { formatDate, formatValue } from '@/lib/format';
import type {
  ComparisonCell,
  ComparisonColumn,
  CompareResponse,
} from '@/types/api';

const STATE_LABEL: Record<string, string> = {
  included: 'Included',
  excluded: 'Not covered',
  conditional: 'Conditional',
  unknown: 'Not established',
  unresolved: 'Unresolved',
};

const STATE_CLASSES: Record<string, string> = {
  included: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  excluded: 'border-zinc-300 bg-zinc-100 text-zinc-700',
  conditional: 'border-amber-300 bg-amber-50 text-amber-900',
  unknown: 'border-slate-300 bg-slate-100 text-slate-700',
  unresolved: 'border-rose-300 bg-rose-50 text-rose-900',
};

/** 'funding.tuition' -> 'Tuition (funding)', 'deadline' -> 'Deadline'. */
export function fieldLabel(field: string): string {
  const pretty = (raw: string): string =>
    raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  const [bucket, name] = field.split('.');
  if (name == null) return pretty(bucket);
  return `${pretty(name)} · ${pretty(bucket)}`;
}

export interface CompareMatrixProps {
  comparison: CompareResponse;
}

function Cell({ children }: { children: ReactNode }): JSX.Element {
  return <div className="px-3 py-3 align-top text-sm text-slate-700">{children}</div>;
}

function StateChip({ state }: { state: string }): JSX.Element | null {
  const css = STATE_CLASSES[state] ?? STATE_CLASSES.unknown;
  const label = STATE_LABEL[state] ?? state.replace(/_/g, ' ');
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${css}`}
    >
      {label}
    </span>
  );
}

function FieldCell({ cell }: { cell: ComparisonCell | undefined }): JSX.Element {
  if (!cell || (cell.state === 'unknown' && cell.value == null)) {
    return <span className="text-slate-600">Not established</span>;
  }
  return (
    <span className="flex flex-col items-start gap-1">
      <StateChip state={cell.state} />
      {cell.value != null && cell.value !== '' ? (
        <span className="whitespace-pre-line text-xs text-slate-700">
          {fieldLabel(cell.field) === 'Deadline' && typeof cell.value === 'string'
            ? formatDate(cell.value)
            : formatValue(cell.value)}
        </span>
      ) : null}
      {cell.note ? <span className="text-xs text-slate-600">{cell.note}</span> : null}
      {cell.checked_at ? (
        <span className="text-[11px] text-slate-500">checked {formatDate(cell.checked_at)}</span>
      ) : null}
    </span>
  );
}

/**
 * FR-7: side-by-side comparison built from the comparison engine's matrix.
 * Every cell names its source and state; gaps stay "Not established" and are
 * never filled with a guess.
 */
export function CompareMatrix({ comparison }: CompareMatrixProps): JSX.Element {
  const columns = comparison.columns;
  const fields = comparison.fields;

  if (columns.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
        Nothing to compare yet.
      </p>
    );
  }

  const gridTemplate = { gridTemplateColumns: `160px repeat(${columns.length}, minmax(180px, 1fr))` };

  return (
    <div className="space-y-4">
      {comparison.notes.length > 0 ? (
        <div className="rounded-md border border-slate-300 bg-slate-50 px-3 py-3 text-sm text-slate-700">
          <p className="font-semibold">Notes</p>
          <ul className="mt-1 list-disc pl-5">
            {comparison.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {comparison.conflicts.length > 0 ? (
        <div role="status" className="rounded-md border border-rose-300 bg-rose-50 px-3 py-3 text-sm text-rose-900">
          <p className="font-semibold">
            {comparison.conflicts.length} unresolved conflict
            {comparison.conflicts.length === 1 ? '' : 's'} across the compared records
          </p>
          <ul className="mt-1 list-disc pl-5">
            {comparison.conflicts.map((conflict, index) => (
              <li key={conflict.id ?? `${conflict.field_name ?? 'field'}-${index}`}>
                {(conflict.field_name ?? '').replace(/_/g, ' ')}: {formatValue(conflict.value_a)} vs{' '}
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
            {columns.map((column) => (
              <div key={column.scholarship_id} className="px-3 py-2">
                {column.name}
                <span className="mt-0.5 block text-xs font-normal normal-case text-slate-600">
                  {column.deadline ? `Deadline ${formatDate(column.deadline)}` : 'No deadline stated'}
                  {column.deadline_state === 'unresolved' ? ' (unresolved)' : ''}
                </span>
              </div>
            ))}
          </div>

          {fields.map((field) => (
            <div
              key={field}
              className="grid border-b border-slate-100 last:border-b-0"
              style={gridTemplate}
            >
              <div className="bg-slate-50/60 px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-600">
                {fieldLabel(field)}
              </div>
              {columns.map((column) => (
                <Cell key={column.scholarship_id}>
                  <FieldCell cell={column.cells[field]} />
                </Cell>
              ))}
            </div>
          ))}

          <div className="grid border-t border-slate-200 bg-slate-50" style={gridTemplate}>
            <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
              Source
            </div>
            {columns.map((column) => (
              <div key={column.scholarship_id} className="px-3 py-2">
                <ClaimChip
                  state={column.deadline_state === 'confirmed' ? 'confirmed' : 'needs_verification'}
                  size="sm"
                />
                <span className="mt-1 block text-xs text-slate-600">
                  {column.source_url ? column.source_url : 'Source not recorded'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default CompareMatrix;
