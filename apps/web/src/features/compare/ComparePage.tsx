import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useCompare } from '@/hooks/useCompare';
import { useScholarships } from '@/hooks/useScholarships';
import { formatDate } from '@/lib/format';
import type { CompareResponse } from '@/types/api';

import { CompareMatrix } from './CompareMatrix';

const MIN_ITEMS = 2;
const MAX_ITEMS = 5;

function buildMarkdown(comparison: CompareResponse): string {
  const lines: string[] = ['# Scholarship comparison', ''];
  for (const item of comparison.items) {
    lines.push(`## ${item.scholarship.name}`);
    lines.push(`Provider: ${item.scholarship.provider_name}`);
    lines.push(`Cycle: ${item.cycle?.cycle_label ?? 'Not stated'}`);
    lines.push(`Deadline: ${formatDate(item.cycle?.deadline_at ?? null)}`);
    lines.push('');
    lines.push('### Requirement verdicts');
    for (const verdict of item.rule_verdicts) {
      lines.push(`- **${verdict.verdict}** — ${verdict.rule_text} (${verdict.reason})`);
    }
    lines.push('');
    lines.push('### Funding components');
    for (const funding of item.funding) {
      lines.push(`- ${funding.component}: ${funding.coverage_status}`);
    }
    lines.push('');
  }
  if (comparison.conflicts.length > 0) {
    lines.push('## Unresolved conflicts');
    for (const conflict of comparison.conflicts) {
      lines.push(`- ${conflict.field_name}: ${String(conflict.value_a)} vs ${String(conflict.value_b)}`);
    }
  }
  return lines.join('\n');
}

export function ComparePage(): JSX.Element {
  const [selected, setSelected] = useState<string[]>([]);
  const scholarshipsQuery = useScholarships({ limit: 50, sort: 'deadline' });
  const compare = useCompare();

  const scholarships = useMemo(() => scholarshipsQuery.data?.items ?? [], [scholarshipsQuery.data]);
  const comparison = compare.data ?? null;

  const toggle = (id: string): void => {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((entry) => entry !== id);
      if (current.length >= MAX_ITEMS) return current;
      return [...current, id];
    });
  };

  const exportMarkdown = (): void => {
    if (!comparison) return;
    const blob = new Blob([buildMarkdown(comparison)], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'scholarmind-comparison.md';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Compare</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Compare {MIN_ITEMS} to {MAX_ITEMS} scholarships side by side: requirement verdicts, funding
          components, deadlines, unknown conditions and how fresh each source is.
        </p>
      </header>

      <Card
        title="Select scholarships"
        description={`Choose between ${MIN_ITEMS} and ${MAX_ITEMS} records.`}
        actions={
          <Button
            loading={compare.isPending}
            disabled={selected.length < MIN_ITEMS}
            onClick={() => compare.mutate({ scholarship_ids: selected })}
          >
            Compare {selected.length > 0 ? `(${selected.length})` : ''}
          </Button>
        }
      >
        {scholarshipsQuery.isLoading ? (
          <div className="space-y-2" role="status" aria-live="polite">
            <span className="sr-only">Loading scholarships…</span>
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : null}

        {scholarshipsQuery.isError ? (
          <ErrorState
            title="Could not load the scholarship list"
            message={scholarshipsQuery.error instanceof Error ? scholarshipsQuery.error.message : undefined}
            onRetry={() => void scholarshipsQuery.refetch()}
          />
        ) : null}

        {!scholarshipsQuery.isLoading && scholarships.length === 0 ? (
          <EmptyState
            title="Nothing to compare yet"
            description="Published opportunities will appear here once they are available."
          />
        ) : null}

        {scholarships.length > 0 ? (
          <ul className="max-h-72 space-y-1 overflow-y-auto">
            {scholarships.map((scholarship) => (
              <li key={scholarship.id}>
                <label className="flex items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-2 focus:ring-sky-500"
                    checked={selected.includes(scholarship.id)}
                    disabled={!selected.includes(scholarship.id) && selected.length >= MAX_ITEMS}
                    onChange={() => toggle(scholarship.id)}
                  />
                  <span>
                    <span className="font-medium text-slate-900">{scholarship.name}</span>
                    <span className="block text-xs text-slate-600">{scholarship.provider_name}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        ) : null}

        {selected.length < MIN_ITEMS ? (
          <p className="mt-3 text-xs text-slate-600">
            Select at least {MIN_ITEMS} scholarships to build a comparison.
          </p>
        ) : null}
      </Card>

      {compare.isError ? (
        <ErrorState
          title="The comparison could not be built"
          message={compare.error instanceof Error ? compare.error.message : undefined}
          onRetry={() => void compare.reset()}
        />
      ) : null}

      <div aria-live="polite">
        {compare.isPending ? (
          <div className="space-y-3" role="status">
            <span className="sr-only">Building comparison…</span>
            <Skeleton className="h-64 w-full rounded-lg" />
          </div>
        ) : null}

        {!compare.isPending && !comparison ? (
          <EmptyState
            title="No comparison yet"
            description="Select the scholarships you want to weigh up and run the comparison."
          />
        ) : null}

        {comparison ? (
          <div className="space-y-3">
            <div className="flex justify-end">
              <Button variant="secondary" onClick={exportMarkdown}>
                Export as Markdown
              </Button>
            </div>
            <CompareMatrix comparison={comparison} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default ComparePage;
