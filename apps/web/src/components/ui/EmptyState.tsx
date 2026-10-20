import type { ReactNode } from 'react';

export interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({ title, description, action, icon }: EmptyStateProps): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
      {icon ? <div aria-hidden="true" className="text-slate-400">{icon}</div> : null}
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      {description ? <p className="max-w-md text-sm text-slate-600">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export default EmptyState;
