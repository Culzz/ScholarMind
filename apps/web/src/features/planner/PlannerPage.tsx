import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import {
  useApplications,
  useCreateApplication,
  useTasks,
} from '@/hooks/useApplications';
import { useScholarship } from '@/hooks/useScholarship';
import { useScholarships } from '@/hooks/useScholarships';
import { useToast } from '@/components/ui/Toast';
import { formatDate } from '@/lib/format';
import type { Application } from '@/types/api';

import { TaskBoard } from './TaskBoard';

const APPLICATION_STATUS_LABEL: Record<string, string | undefined> = {
  planning: 'Planning',
  preparing: 'Preparing',
  submitted: 'Submitted',
  accepted: 'Accepted',
  rejected: 'Not successful',
  withdrawn: 'Withdrawn',
  closed: 'Closed',
};

function NewApplicationDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (application: Application) => void;
}): JSX.Element {
  const [scholarshipId, setScholarshipId] = useState<string>('');
  const [cycleId, setCycleId] = useState<string>('');
  const [notes, setNotes] = useState<string>('');

  const scholarshipsQuery = useScholarships({ limit: 50, sort: 'deadline' });
  const detailQuery = useScholarship(scholarshipId || undefined);
  const createApplication = useCreateApplication();

  const scholarships = useMemo(() => scholarshipsQuery.data?.items ?? [], [scholarshipsQuery.data]);
  const cycles = useMemo(() => detailQuery.data?.cycles ?? [], [detailQuery.data]);

  useEffect(() => {
    setCycleId('');
  }, [scholarshipId]);

  const handleSubmit = async (): Promise<void> => {
    if (!scholarshipId || !cycleId) return;
    const created = await createApplication.mutateAsync({
      scholarship_id: scholarshipId,
      cycle_id: cycleId,
      notes: notes || undefined,
    });
    onCreated(created);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New application plan"
      description="A plan targets one cycle. Tasks are generated from that cycle's document requirements."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={createApplication.isPending}
            disabled={!scholarshipId || !cycleId}
            onClick={() => void handleSubmit()}
          >
            Create plan
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {scholarshipsQuery.isLoading ? <Skeleton className="h-9 w-full" /> : null}
        {scholarshipsQuery.isError ? (
          <ErrorState
            title="Could not load scholarships"
            message={scholarshipsQuery.error instanceof Error ? scholarshipsQuery.error.message : undefined}
            onRetry={() => void scholarshipsQuery.refetch()}
          />
        ) : null}

        <div>
          <label htmlFor="plan-scholarship" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Scholarship
          </label>
          <select
            id="plan-scholarship"
            value={scholarshipId}
            onChange={(event) => setScholarshipId(event.target.value)}
            className="block w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm"
          >
            <option value="">Select a scholarship…</option>
            {scholarships.map((scholarship) => (
              <option key={scholarship.id} value={scholarship.id}>
                {scholarship.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="plan-cycle" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Cycle
          </label>
          {scholarshipId && detailQuery.isLoading ? <Skeleton className="h-9 w-full" /> : null}
          <select
            id="plan-cycle"
            value={cycleId}
            onChange={(event) => setCycleId(event.target.value)}
            disabled={!scholarshipId}
            className="block w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm disabled:bg-slate-100"
          >
            <option value="">{scholarshipId ? 'Select a cycle…' : 'Choose a scholarship first'}</option>
            {cycles.map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.cycle_label} — deadline {formatDate(cycle.deadline_at)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="plan-notes" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Notes
          </label>
          <textarea
            id="plan-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={3}
            className="block w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm"
          />
        </div>

        {createApplication.isError ? (
          <ErrorState
            title="Could not create the plan"
            message={createApplication.error instanceof Error ? createApplication.error.message : undefined}
            onRetry={() => void createApplication.reset()}
          />
        ) : null}
      </div>
    </Dialog>
  );
}

export function PlannerPage(): JSX.Element {
  const applicationsQuery = useApplications();
  const tasksQuery = useTasks();
  const toast = useToast();
  const [selectedApplicationId, setSelectedApplicationId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const applications = useMemo(() => applicationsQuery.data?.items ?? [], [applicationsQuery.data]);
  const tasks = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data]);

  useEffect(() => {
    if (selectedApplicationId && applications.some((entry) => entry.id === selectedApplicationId)) return;
    setSelectedApplicationId(applications[0]?.id ?? null);
  }, [applications, selectedApplicationId]);

  const exportPlan = (): void => {
    const lines: string[] = ['# Application plan', ''];
    for (const application of applications) {
      lines.push(`## ${application.scholarship_name ?? application.id}`);
      lines.push(`Cycle: ${application.cycle_label ?? application.cycle_id}`);
      lines.push(`Target deadline: ${formatDate(application.target_deadline)}`);
      lines.push(`Status: ${APPLICATION_STATUS_LABEL[application.status] ?? application.status}`);
      lines.push('');
      lines.push('### Tasks');
      for (const task of tasks.filter((entry) => entry.application_id === application.id)) {
        lines.push(`- [${task.status === 'done' ? 'x' : ' '}] ${task.title} (due ${formatDate(task.due_at)})`);
      }
      lines.push('');
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'scholarmind-application-plan.md';
    link.click();
    URL.revokeObjectURL(url);
    toast.push({ title: 'Plan exported', description: 'Your plan was downloaded as Markdown.', tone: 'success' });
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Planner</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Turn a shortlist into a dated plan. Deadlines shown here are the cycle deadlines we could
            confirm from an official source.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={exportPlan} disabled={applications.length === 0}>
            Export plan
          </Button>
          <Button onClick={() => setDialogOpen(true)}>New plan</Button>
        </div>
      </header>

      <Card title="Your application plans">
        {applicationsQuery.isLoading ? (
          <div className="space-y-2" role="status" aria-live="polite">
            <span className="sr-only">Loading plans…</span>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : null}

        {applicationsQuery.isError ? (
          <ErrorState
            title="Could not load your plans"
            message={applicationsQuery.error instanceof Error ? applicationsQuery.error.message : undefined}
            onRetry={() => void applicationsQuery.refetch()}
          />
        ) : null}

        {!applicationsQuery.isLoading && !applicationsQuery.isError && applications.length === 0 ? (
          <EmptyState
            title="No plans yet"
            description="Create a plan for a cycle and we will generate the checklist of documents and form tasks."
            action={<Button onClick={() => setDialogOpen(true)}>Create your first plan</Button>}
          />
        ) : null}

        {applications.length > 0 ? (
          <ul className="space-y-2">
            {applications.map((application) => (
              <li key={application.id}>
                <button
                  type="button"
                  onClick={() => setSelectedApplicationId(application.id)}
                  aria-pressed={selectedApplicationId === application.id}
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2 ${
                    selectedApplicationId === application.id
                      ? 'border-sky-600 bg-sky-50'
                      : 'border-slate-200 bg-white hover:bg-slate-50'
                  }`}
                >
                  <span className="font-medium text-slate-900">
                    {application.scholarship_name ?? 'Scholarship'}
                  </span>
                  <span className="ml-2 text-xs text-slate-600">
                    {application.cycle_label ?? ''} ·{' '}
                    {APPLICATION_STATUS_LABEL[application.status] ?? application.status} · deadline{' '}
                    {formatDate(application.target_deadline)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      <TaskBoard applicationId={selectedApplicationId ?? undefined} />

      <NewApplicationDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={(application) => {
          toast.push({
            title: 'Plan created',
            description: `Tasks were generated for ${application.scholarship_name ?? 'your plan'}.`,
            tone: 'success',
          });
          setSelectedApplicationId(application.id);
        }}
      />
    </div>
  );
}

export default PlannerPage;
