import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { ClaimChip } from '@/components/ClaimChip';
import { DeadlinePill } from '@/components/DeadlinePill';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useApplications, useTasks } from '@/hooks/useApplications';
import { useProfile } from '@/hooks/useProfile';
import { useRecommendations } from '@/hooks/useRecommendations';
import { useScholarships } from '@/hooks/useScholarships';
import { formatDate } from '@/lib/format';

const MISSING_PROFILE_FIELDS: Array<{ key: string; label: string; get: (profile: {
  age: number | null;
  gpa_value: number | null;
  work_experience_months: number | null;
  current_institution: string | null;
  fields_of_study: string[];
  languages: unknown[];
}) => boolean }> = [
  { key: 'age', label: 'Age', get: (profile) => profile.age === null },
  {
    key: 'gpa_value',
    label: 'Grade and scale',
    get: (profile) => profile.gpa_value === null,
  },
  {
    key: 'work_experience_months',
    label: 'Work experience',
    get: (profile) => profile.work_experience_months === null,
  },
  {
    key: 'current_institution',
    label: 'Current institution',
    get: (profile) => profile.current_institution === null,
  },
  {
    key: 'fields_of_study',
    label: 'Fields of study',
    get: (profile) => profile.fields_of_study.length === 0,
  },
  { key: 'languages', label: 'Languages', get: (profile) => profile.languages.length === 0 },
];

export function DashboardPage(): JSX.Element {
  const recommendations = useRecommendations();
  const tasks = useTasks();
  const applications = useApplications();
  const profile = useProfile();
  const scholarships = useScholarships({ limit: 5, sort: 'verification' });

  const topRecommendations = useMemo(
    () => (recommendations.data?.items ?? []).slice(0, 3),
    [recommendations.data],
  );
  const openTasks = useMemo(
    () =>
      (tasks.data?.items ?? [])
        .filter((task) => task.status !== 'done' && task.status !== 'skipped')
        .slice(0, 5),
    [tasks.data],
  );
  const missingFields = useMemo(() => {
    const data = profile.data;
    if (!data) return [];
    return MISSING_PROFILE_FIELDS.filter((field) => field.get(data)).map((field) => field.label);
  }, [profile.data]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Dashboard</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          What needs your attention: opportunities that match your profile, deadlines coming up,
          profile gaps that are blocking verdicts, and how fresh our sources are.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Priority opportunities"
          description="A prioritisation aid based on your profile — not a probability of admission."
        >
          {recommendations.isLoading ? (
            <div className="space-y-2" role="status" aria-live="polite">
              <span className="sr-only">Loading recommendations…</span>
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : null}

          {recommendations.isError ? (
            <ErrorState
              title="Could not load your shortlist"
              message={recommendations.error instanceof Error ? recommendations.error.message : undefined}
              onRetry={() => void recommendations.refetch()}
            />
          ) : null}

          {!recommendations.isLoading && !recommendations.isError && topRecommendations.length === 0 ? (
            <EmptyState
              title="No recommendations yet"
              description="Complete your profile so we can rank the opportunities that fit you."
              action={
                <Link
                  to="/eligibility"
                  className="inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
                >
                  Complete your profile
                </Link>
              }
            />
          ) : null}

          {topRecommendations.length > 0 ? (
            <ul className="space-y-3">
              {topRecommendations.map((recommendation) => (
                <li key={recommendation.scholarship_id} className="rounded-md border border-slate-200 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <Link
                      to={`/scholarships/${recommendation.scholarship_id}`}
                      className="font-medium text-slate-900 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
                    >
                      {recommendation.scholarship.name}
                    </Link>
                    <Badge tone="sky">Priority rank {recommendation.rank}</Badge>
                  </div>
                  {recommendation.cycle ? (
                    <div className="mt-2">
                      <DeadlinePill
                        deadline={recommendation.cycle.deadline_at}
                        claimState={recommendation.cycle.claim_state}
                        rawText={recommendation.cycle.deadline_raw_text}
                      />
                    </div>
                  ) : null}
                  <ul className="mt-2 space-y-1 text-xs text-slate-600">
                    {recommendation.factors.slice(0, 3).map((factor) => (
                      <li key={factor.key}>
                        {factor.label}: {factor.value.toFixed(2)} × weight {factor.weight.toFixed(2)}
                        {factor.detail ? ` — ${factor.detail}` : ''}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>

        <Card
          title="Upcoming tasks"
          description="Deadlines and document steps from your application plans."
          actions={
            <Link
              to="/planner"
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
            >
              Open planner
            </Link>
          }
        >
          {tasks.isLoading ? (
            <div className="space-y-2" role="status" aria-live="polite">
              <span className="sr-only">Loading tasks…</span>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : null}

          {tasks.isError ? (
            <ErrorState
              title="Could not load your tasks"
              message={tasks.error instanceof Error ? tasks.error.message : undefined}
              onRetry={() => void tasks.refetch()}
            />
          ) : null}

          {!tasks.isLoading && !tasks.isError && openTasks.length === 0 ? (
            <EmptyState
              title="Nothing due"
              description="Create an application plan and we will back-schedule the document checklist from the deadline."
            />
          ) : null}

          {openTasks.length > 0 ? (
            <ul className="space-y-2">
              {openTasks.map((task) => (
                <li key={task.id} className="flex items-start justify-between gap-3 text-sm">
                  <span className="min-w-0">
                    <span className="font-medium text-slate-900">{task.title}</span>
                    <span className="block text-xs text-slate-600">{task.task_type}</span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-700">{formatDate(task.due_at)}</span>
                </li>
              ))}
            </ul>
          ) : null}

          {applications.data && applications.data.items.length > 0 ? (
            <p className="mt-3 text-xs text-slate-600">
              {applications.data.items.length} active plan
              {applications.data.items.length === 1 ? '' : 's'}.
            </p>
          ) : null}
        </Card>

        <Card title="Profile gaps" description="Missing facts are what turn verdicts into “unknown”.">
          {profile.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : null}

          {profile.isError ? (
            <ErrorState
              title="Could not load your profile"
              message={profile.error instanceof Error ? profile.error.message : undefined}
              onRetry={() => void profile.refetch()}
            />
          ) : null}

          {!profile.isLoading && !profile.isError && missingFields.length === 0 ? (
            <p className="text-sm text-slate-700">
              Your profile covers the fields we ask for. Every requirement can now be checked against a
              fact you supplied.
            </p>
          ) : null}

          {missingFields.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-slate-700">
              {missingFields.map((field) => (
                <li key={field}>{field}</li>
              ))}
            </ul>
          ) : null}

          <Link
            to="/eligibility"
            className="mt-3 inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
          >
            Update profile
          </Link>
        </Card>

        <Card title="Source freshness" description="How recently we confirmed the official pages.">
          {scholarships.isLoading ? <Skeleton className="h-20 w-full" /> : null}

          {scholarships.isError ? (
            <ErrorState
              title="Could not load the source list"
              message={scholarships.error instanceof Error ? scholarships.error.message : undefined}
              onRetry={() => void scholarships.refetch()}
            />
          ) : null}

          {!scholarships.isLoading && !scholarships.isError ? (
            <ul className="space-y-2">
              {(scholarships.data?.items ?? []).map((scholarship) => (
                <li
                  key={scholarship.id}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span className="min-w-0 truncate text-slate-800">{scholarship.name}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-slate-600">
                      {formatDate(scholarship.source_last_checked_at ?? null)}
                    </span>
                    {scholarship.current_cycle ? (
                      <ClaimChip state={scholarship.current_cycle.claim_state} size="sm" />
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          <p className="mt-3 text-xs text-slate-600">
            Deadline states are shown on every record. A source that could not be reached is marked
            stale rather than closed.
          </p>
        </Card>
      </div>
    </div>
  );
}

export default DashboardPage;
