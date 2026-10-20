import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { useScholarships } from '@/hooks/useScholarships';
import { formatDateTime } from '@/lib/format';
import type { ScholarshipFilters } from '@/types/api';

import { FilterPanel } from './FilterPanel';
import { ScholarshipCard } from './ScholarshipCard';

const DEFAULT_FILTERS: ScholarshipFilters = {
  q: '',
  sort: 'deadline',
  verification: '',
};

/**
 * FR-1: discovery surface. Handles loading, empty, error and stale states.
 */
export function DiscoveryPage(): JSX.Element {
  const [filters, setFilters] = useState<ScholarshipFilters>(DEFAULT_FILTERS);
  const [cursorHistory, setCursorHistory] = useState<string[]>([]);

  const query = useScholarships(filters);
  const items = query.data?.items ?? [];

  const stale = query.isFetching && !query.isLoading && Boolean(query.data);
  const lastUpdated = useMemo(() => (query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null), [
    query.dataUpdatedAt,
  ]);

  const handleReset = (): void => {
    setFilters(DEFAULT_FILTERS);
    setCursorHistory([]);
  };

  const handleLoadMore = (): void => {
    const next = query.data?.next_cursor ?? null;
    if (!next) return;
    setCursorHistory((history) => [...history, next]);
    setFilters((current) => ({ ...current, cursor: next }));
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Discover</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Search verified opportunities across funders, universities and government schemes. Every card
          links to the official source and shows when that source was last checked.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <aside>
          <FilterPanel
            filters={filters}
            onChange={(next) => {
              setCursorHistory([]);
              setFilters(next);
            }}
            onReset={handleReset}
            resultCount={query.data ? items.length : null}
          />
        </aside>

        <section aria-label="Scholarship results" className="space-y-4">
          <div
            className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600"
            aria-live="polite"
          >
            <p>
              {query.isLoading
                ? 'Loading results…'
                : `${items.length} result${items.length === 1 ? '' : 's'}${
                    query.data?.total ? ` of ${query.data.total}` : ''
                  }`}
            </p>
            {lastUpdated ? <p>Results last refreshed {formatDateTime(lastUpdated.toISOString())}</p> : null}
          </div>

          {stale ? (
            <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              These results are being refreshed — the list below may be out of date.
            </p>
          ) : null}

          {query.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <SkeletonCard key={index} lines={4} />
              ))}
            </div>
          ) : null}

          {query.isError ? (
            <ErrorState
              title="Could not load the scholarship list"
              message={
                query.error instanceof Error
                  ? query.error.message
                  : 'The API did not respond. The results below may be out of date.'
              }
              onRetry={() => void query.refetch()}
            />
          ) : null}

          {!query.isLoading && !query.isError && items.length === 0 ? (
            <EmptyState
              title="No scholarships match these filters"
              description="Try widening the deadline window, clearing the keyword, or resetting the filters. Expired cycles are excluded from open searches by default."
              action={
                <Button variant="secondary" onClick={handleReset}>
                  Reset filters
                </Button>
              }
            />
          ) : null}

          {items.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              {items.map((scholarship) => (
                <ScholarshipCard key={scholarship.id} scholarship={scholarship} />
              ))}
            </div>
          ) : null}

          {query.data?.next_cursor ? (
            <div className="flex justify-center pt-2">
              <Button variant="secondary" loading={query.isFetching} onClick={handleLoadMore}>
                Load more results
              </Button>
            </div>
          ) : null}

          {cursorHistory.length > 0 ? (
            <p className="text-center text-xs text-slate-600">
              Page {cursorHistory.length + 1} of results.
            </p>
          ) : null}
        </section>
      </div>

      <Card title="How to read these results">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>A deadline marked “Not established” means we could not find it in the official material.</li>
          <li>A deadline marked “Needs verification” means two official sources disagree — both are shown on the detail page.</li>
          <li>“Stale” means the source could not be reached on the last check; the last known date is still shown with its check time.</li>
        </ul>
      </Card>
    </div>
  );
}

export default DiscoveryPage;
