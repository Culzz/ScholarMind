import { useMemo, useState } from 'react';

import { EligibilityRow, VERDICT_LABEL } from '@/components/EligibilityRow';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useEvaluateEligibility } from '@/hooks/useAssessment';
import { useProfile, useUpdateProfile } from '@/hooks/useProfile';
import { useScholarships } from '@/hooks/useScholarships';
import { humaniseField } from '@/lib/format';
import type { Assessment, ProfileInput, Verdict } from '@/types/api';

import { ProfileForm } from './ProfileForm';

const OVERALL_LABEL: Record<string, string | undefined> = {
  eligible: 'Every mandatory requirement is met',
  likely_eligible: 'Mandatory requirements are met, but some optional ones are unknown',
  unknown: 'Not enough information to decide',
  not_eligible: 'A mandatory requirement is not met',
  needs_review: 'A requirement needs a human review',
};

const OVERALL_TONE: Record<string, string | undefined> = {
  eligible: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  likely_eligible: 'border-emerald-200 bg-emerald-50/60 text-emerald-900',
  unknown: 'border-amber-300 bg-amber-50 text-amber-900',
  not_eligible: 'border-rose-300 bg-rose-50 text-rose-900',
  needs_review: 'border-slate-400 bg-slate-100 text-slate-900',
};

const VERDICT_ORDER: Verdict[] = ['satisfied', 'not_satisfied', 'unknown', 'needs_review'];

function VerdictCounts({ assessment }: { assessment: Assessment }): JSX.Element {
  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {VERDICT_ORDER.map((verdict) => {
        const count = assessment.verdict_counts?.[verdict] ?? 0;
        return (
          <li
            key={verdict}
            className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
          >
            <span className="font-semibold text-slate-900">{count}</span>{' '}
            {VERDICT_LABEL[verdict].toLowerCase()}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * FR-3: profile + rule-by-rule analysis. There is deliberately no single
 * "match percentage" anywhere on this page — only per-rule verdicts with
 * reasons, evidence and the facts that are still missing.
 */
export function EligibilityPage(): JSX.Element {
  const profileQuery = useProfile();
  const updateProfile = useUpdateProfile();
  const evaluate = useEvaluateEligibility();
  const scholarshipsQuery = useScholarships({ limit: 25, sort: 'deadline' });

  const [selected, setSelected] = useState<string[]>([]);
  const [pendingProfile, setPendingProfile] = useState<ProfileInput | null>(null);

  const scholarships = useMemo(() => scholarshipsQuery.data?.items ?? [], [scholarshipsQuery.data]);

  const runEvaluation = async (input: ProfileInput): Promise<void> => {
    setPendingProfile(input);
    try {
      await updateProfile.mutateAsync(input);
    } catch {
      // The profile could not be saved — still evaluate against the typed values
      // so the student gets an answer, but surface the failure below.
    }
    try {
      await evaluate.mutateAsync({
        profile: input,
        scholarship_ids: selected.length > 0 ? selected : undefined,
      });
    } finally {
      setPendingProfile(null);
    }
  };

  const handleSave = async (input: ProfileInput): Promise<void> => {
    try {
      await updateProfile.mutateAsync(input);
    } catch {
      // Error surfaces through the mutation state below.
    }
  };

  const assessments = evaluate.data?.assessments ?? [];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Eligibility</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Each requirement of a scholarship cycle is checked separately against your profile. A missing
          fact produces an “not enough information” verdict — it is never treated as a pass.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section className="space-y-4" aria-label="Profile">
          {profileQuery.isLoading ? (
            <Skeleton className="h-96 w-full rounded-lg" />
          ) : (
            <ProfileForm
              profile={profileQuery.data}
              onSubmit={handleSave}
              saving={updateProfile.isPending}
              onEvaluate={runEvaluation}
              evaluating={evaluate.isPending}
              submitLabel="Save profile"
            />
          )}

          {updateProfile.isError ? (
            <ErrorState
              title="Could not save your profile"
              message={updateProfile.error instanceof Error ? updateProfile.error.message : undefined}
              onRetry={() => void updateProfile.reset()}
            />
          ) : null}

          {profileQuery.data ? (
            <Card title="Profile completeness" description="This measures your profile, not your eligibility.">
              <p className="text-sm text-slate-700">
                {Math.round((profileQuery.data.completeness ?? 0) * 100)}% of the fields we ask for are
                filled in. Filling the gaps below turns “not enough information” verdicts into real
                answers.
              </p>
            </Card>
          ) : null}
        </section>

        <section className="space-y-4" aria-label="Evaluation">
          <Card
            title="Choose what to evaluate"
            description="Pick the scholarships you want verdicts for. Leave everything unselected to evaluate your whole shortlist."
          >
            {scholarshipsQuery.isLoading ? (
              <div className="space-y-2" role="status" aria-live="polite">
                <span className="sr-only">Loading scholarships…</span>
                <Skeleton className="h-8 w-full" />
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

            {!scholarshipsQuery.isLoading && !scholarshipsQuery.isError && scholarships.length === 0 ? (
              <EmptyState
                title="No scholarships to evaluate yet"
                description="Once opportunities are published you can select them here for a rule-by-rule analysis."
              />
            ) : null}

            {scholarships.length > 0 ? (
              <fieldset>
                <legend className="sr-only">Scholarships to evaluate</legend>
                <ul className="max-h-64 space-y-1 overflow-y-auto">
                  {scholarships.map((scholarship) => (
                    <li key={scholarship.id}>
                      <label className="flex items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50">
                        <input
                          type="checkbox"
                          className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-2 focus:ring-sky-500"
                          checked={selected.includes(scholarship.id)}
                          onChange={(event) =>
                            setSelected((current) =>
                              event.target.checked
                                ? [...current, scholarship.id]
                                : current.filter((id) => id !== scholarship.id),
                            )
                          }
                        />
                        <span>
                          <span className="font-medium text-slate-900">{scholarship.name}</span>
                          <span className="block text-xs text-slate-600">{scholarship.provider_name}</span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            ) : null}

            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="secondary"
                loading={evaluate.isPending}
                onClick={() => void runEvaluation(pendingProfile ?? {})}
              >
                Evaluate with saved profile
              </Button>
              {selected.length > 0 ? (
                <Button variant="ghost" onClick={() => setSelected([])}>
                  Clear selection ({selected.length})
                </Button>
              ) : null}
            </div>

            {evaluate.isError ? (
              <div className="mt-3">
                <ErrorState
                  title="The evaluation could not be completed"
                  message={evaluate.error instanceof Error ? evaluate.error.message : undefined}
                  onRetry={() => void evaluate.reset()}
                />
              </div>
            ) : null}
          </Card>

          <div aria-live="polite">
            {evaluate.isPending ? (
              <div className="space-y-3" role="status">
                <span className="sr-only">Evaluating requirements…</span>
                <Skeleton className="h-32 w-full rounded-lg" />
                <Skeleton className="h-32 w-full rounded-lg" />
              </div>
            ) : null}

            {!evaluate.isPending && assessments.length === 0 ? (
              <EmptyState
                title="No verdicts yet"
                description="Run an evaluation to see a verdict, a reason and the supporting evidence for every requirement."
              />
            ) : null}

            {assessments.map((assessment) => (
              <Card
                key={assessment.id}
                className="mb-4"
                title={assessment.scholarship_name ?? assessment.cycle_label ?? 'Assessment'}
                description={`${assessment.engine_version} · rule set v${assessment.ruleset_version}`}
              >
                <p
                  className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${
                    OVERALL_TONE[assessment.overall_status] ??
                    'border-slate-300 bg-slate-100 text-slate-900'
                  }`}
                >
                  {OVERALL_LABEL[assessment.overall_status] ?? assessment.overall_status}
                </p>

                <VerdictCounts assessment={assessment} />

                {assessment.missing_fields.length > 0 ? (
                  <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
                      What is still missing
                    </p>
                    <ul className="mt-1 list-disc pl-5 text-sm text-amber-900">
                      {assessment.missing_fields.map((field) => (
                        <li key={field}>{humaniseField(field)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <ul className="mt-4 space-y-3">
                  {assessment.results.map((result) => (
                    <EligibilityRow key={result.rule_id} result={result} />
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

export default EligibilityPage;
