import { Link, useNavigate, useParams } from 'react-router-dom';

import { ClaimChip } from '@/components/ClaimChip';
import { FundingBreakdown } from '@/components/FundingBreakdown';
import { SourceCard } from '@/components/SourceCard';
import { EligibilityRow } from '@/components/EligibilityRow';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs } from '@/components/ui/Tabs';
import { useChangeHistory, useScholarship } from '@/hooks/useScholarship';
import { formatDateTime } from '@/lib/format';

import { ChangeHistory } from './ChangeHistory';
import { CycleList } from './CycleList';

export function ScholarshipDetailPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const detail = useScholarship(id);
  const history = useChangeHistory(id);

  if (detail.isLoading) {
    return (
      <div className="space-y-4" role="status" aria-live="polite">
        <span className="sr-only">Loading scholarship…</span>
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="space-y-4">
        <ErrorState
          title="Could not load this scholarship"
          message={
            detail.error instanceof Error
              ? detail.error.message
              : 'The API did not respond. Some facts below may be out of date.'
          }
          onRetry={() => void detail.refetch()}
        />
        <Link
          to="/discover"
          className="inline-block rounded text-sm font-medium text-sky-700 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
        >
          Back to discovery
        </Link>
      </div>
    );
  }

  const { scholarship, cycles, funding_components, sources, rules, latest_assessment } = detail.data;
  const firstCycle = cycles.length > 0 ? cycles[0] : null;
  const currentCycle = cycles.find((cycle) => cycle.is_current) ?? firstCycle;
  const assessment = latest_assessment;
  const stale = detail.isFetching && !detail.isLoading;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            to="/discover"
            className="text-sm font-medium text-sky-700 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
          >
            ← Back to discovery
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{scholarship.name}</h1>
          <p className="mt-1 text-sm text-slate-600">
            {scholarship.provider_name}
            {scholarship.provider_country_iso3 ? ` · ${scholarship.provider_country_iso3}` : ''} ·{' '}
            {scholarship.study_levels.length > 0
              ? scholarship.study_levels.join(', ').replace(/_/g, ' ')
              : 'Degree levels not stated'}
          </p>
          {scholarship.description ? (
            <p className="mt-2 max-w-3xl text-sm text-slate-700">{scholarship.description}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          {scholarship.website_url ? (
            <a
              href={scholarship.website_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
            >
              Official page
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : null}
          <Button
            variant="secondary"
            onClick={() => navigate(`/assistant?scholarship=${encodeURIComponent(scholarship.id)}`)}
          >
            Ask about this
          </Button>
        </div>
      </header>

      {stale ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Refreshing this record — facts below were last confirmed at{' '}
          {formatDateTime(new Date(detail.dataUpdatedAt).toISOString())}.
        </p>
      ) : null}

      <Tabs
        label="Scholarship sections"
        items={[
          {
            id: 'overview',
            label: 'Overview',
            content: (
              <div className="space-y-5">
                <Card title="Cycles" description="Deadlines and status live on the cycle, not on the award.">
                  <CycleList cycles={cycles} currentCycleId={currentCycle?.id ?? null} />
                </Card>

                <Card
                  title="Funding breakdown"
                  description="Each component is shown separately — there is no single “fully funded” flag."
                >
                  <FundingBreakdown components={funding_components} />
                </Card>

                <Card title="Sources" description="Where each fact came from, and when it was last checked.">
                  {sources.length === 0 ? (
                    <EmptyState
                      title="No sources recorded"
                      description="We cannot show any claim as confirmed until an official source is attached."
                    />
                  ) : (
                    <ul className="space-y-3">
                      {sources.map((source) => (
                        <li key={source.id}>
                          <SourceCard source={source} />
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            ),
          },
          {
            id: 'eligibility',
            label: 'Eligibility',
            content: (
              <div className="space-y-5">
                <Card
                  title="Requirements"
                  description="Rule-by-rule requirements as published by the funder."
                >
                  {rules.length === 0 ? (
                    <EmptyState
                      title="No typed rules extracted yet"
                      description="Requirements will appear here once they are extracted and validated against the source text."
                    />
                  ) : (
                    <ul className="space-y-3">
                      {rules.map((rule) => (
                        <li key={rule.id} className="rounded-md border border-slate-200 bg-white p-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <p className="text-sm font-medium text-slate-900">{rule.rule_text}</p>
                            <span className="text-xs text-slate-600">
                              {rule.comparability} · {rule.kind.replace(/_/g, ' ')}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-slate-600">
                            Evidence ids: {rule.evidence_ids.length > 0 ? rule.evidence_ids.join(', ') : 'none recorded'}
                          </p>
                          {rule.ambiguity_flag ? (
                            <p className="mt-2">
                              <ClaimChip
                                state="needs_verification"
                                size="sm"
                                label="Wording ambiguous — a human check is required"
                              />
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>

                <Card
                  title="Your verdicts"
                  description="Produced by the deterministic rule engine from your profile. There is no single match score."
                >
                  {!assessment ? (
                    <EmptyState
                      title="No assessment yet"
                      description="Complete your profile and run an evaluation to see a verdict for each requirement."
                      action={
                        <Link
                          to="/eligibility"
                          className="inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
                        >
                          Go to eligibility
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="space-y-3">
                      {assessment.results.map((result) => (
                        <EligibilityRow key={result.rule_id} result={result} />
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            ),
          },
          {
            id: 'changes',
            label: 'Change history',
            content: (
              <div className="space-y-4">
                {history.isLoading ? (
                  <div className="space-y-3" role="status" aria-live="polite">
                    <span className="sr-only">Loading change history…</span>
                    <Skeleton className="h-24 w-full rounded-lg" />
                    <Skeleton className="h-24 w-full rounded-lg" />
                  </div>
                ) : null}
                {history.isError ? (
                  <ErrorState
                    title="Could not load the change history"
                    message={history.error instanceof Error ? history.error.message : undefined}
                    onRetry={() => void history.refetch()}
                  />
                ) : null}
                {history.data ? (
                  <>
                    {history.data.conflicts.length > 0 ? (
                      <div
                        role="status"
                        className="rounded-md border border-rose-300 bg-rose-50 px-3 py-3 text-sm text-rose-900"
                      >
                        <p className="font-semibold">
                          {history.data.conflicts.length} unresolved conflict
                          {history.data.conflicts.length === 1 ? '' : 's'} on this record
                        </p>
                        <ul className="mt-1 list-disc pl-5">
                          {history.data.conflicts.map((conflict) => (
                            <li key={conflict.id}>
                              {conflict.field_name.replace(/_/g, ' ')}: {String(conflict.value_a)} vs{' '}
                              {String(conflict.value_b)} — neither value is asserted as final.
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <ChangeHistory changes={history.data.changes} />
                  </>
                ) : null}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

export default ScholarshipDetailPage;
