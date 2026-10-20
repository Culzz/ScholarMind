import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useTasks, useUpdateTask } from '@/hooks/useApplications';
import { formatDate, formatRelativeDeadline } from '@/lib/format';
import type { ApplicationTask, TaskStatus } from '@/types/api';

const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
  blocked: 'Blocked',
  skipped: 'Skipped',
};

const STATUS_TONE: Record<TaskStatus, 'neutral' | 'sky' | 'emerald' | 'rose' | 'zinc'> = {
  todo: 'neutral',
  in_progress: 'sky',
  done: 'emerald',
  blocked: 'rose',
  skipped: 'zinc',
};

export interface TaskBoardProps {
  /** When set, only tasks for this application are shown. */
  applicationId?: string;
}

export function TaskBoard({ applicationId }: TaskBoardProps): JSX.Element {
  const tasksQuery = useTasks(applicationId);
  const updateTask = useUpdateTask();
  const [showDone, setShowDone] = useState(true);

  const tasks = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data]);
  const visible = useMemo(
    () => (showDone ? tasks : tasks.filter((task) => task.status !== 'done' && task.status !== 'skipped')),
    [tasks, showDone],
  );

  const toggleDone = (task: ApplicationTask): void => {
    const nextStatus: TaskStatus = task.status === 'done' ? 'todo' : 'done';
    updateTask.mutate({ id: task.id, status: nextStatus });
  };

  return (
    <Card
      title="Task checklist"
      description="Tasks are back-scheduled from the real deadline using document lead times."
      actions={
        <Button variant="ghost" size="sm" onClick={() => setShowDone((value) => !value)}>
          {showDone ? 'Hide completed' : 'Show completed'}
        </Button>
      }
    >
      {tasksQuery.isLoading ? (
        <div className="space-y-2" role="status" aria-live="polite">
          <span className="sr-only">Loading tasks…</span>
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : null}

      {tasksQuery.isError ? (
        <ErrorState
          title="Could not load your tasks"
          message={tasksQuery.error instanceof Error ? tasksQuery.error.message : undefined}
          onRetry={() => void tasksQuery.refetch()}
        />
      ) : null}

      {!tasksQuery.isLoading && !tasksQuery.isError && tasks.length === 0 ? (
        <EmptyState
          title="No tasks yet"
          description="Create an application plan and we will generate the document checklist from the cycle requirements."
        />
      ) : null}

      {updateTask.isError ? (
        <div className="mb-3">
          <ErrorState
            title="Could not update that task"
            message={updateTask.error instanceof Error ? updateTask.error.message : undefined}
            onRetry={() => void updateTask.reset()}
          />
        </div>
      ) : null}

      {visible.length > 0 ? (
        <ul className="space-y-2">
          {visible.map((task) => {
            const relative = formatRelativeDeadline(task.due_at);
            const overdue = relative.tone === 'past';
            return (
              <li
                key={task.id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-slate-200 bg-white p-3"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <input
                    type="checkbox"
                    id={`task-${task.id}`}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-2 focus:ring-sky-500"
                    checked={task.status === 'done'}
                    disabled={updateTask.isPending}
                    onChange={() => toggleDone(task)}
                  />
                  <div className="min-w-0">
                    <label
                      htmlFor={`task-${task.id}`}
                      className={`text-sm font-medium ${task.status === 'done' ? 'text-slate-500 line-through' : 'text-slate-900'}`}
                    >
                      {task.title}
                    </label>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      <Badge tone={STATUS_TONE[task.status]}>{STATUS_LABEL[task.status]}</Badge>
                      <Badge tone="neutral">{task.task_type}</Badge>
                      {task.is_auto_generated ? <Badge tone="sky">auto-generated</Badge> : null}
                      {task.doc_type ? <Badge tone="neutral">{task.doc_type}</Badge> : null}
                    </p>
                    {task.notes ? <p className="mt-1 text-xs text-slate-700">{task.notes}</p> : null}
                    {task.depends_on_task_id ? (
                      <p className="mt-1 text-xs text-slate-600">
                        Depends on another task in this plan.
                      </p>
                    ) : null}
                  </div>
                </div>

                <div className="text-right text-xs">
                  <p className={`font-medium ${overdue ? 'text-rose-700' : 'text-slate-700'}`}>
                    {formatDate(task.due_at)}
                  </p>
                  <p className={overdue ? 'text-rose-700' : 'text-slate-600'}>{relative.label}</p>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </Card>
  );
}

export default TaskBoard;
