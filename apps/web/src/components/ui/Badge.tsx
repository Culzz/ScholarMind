import type { ReactNode } from 'react';

export type BadgeTone =
  | 'neutral'
  | 'emerald'
  | 'amber'
  | 'rose'
  | 'slate'
  | 'zinc'
  | 'sky'
  | 'violet';

export interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  title?: string;
}

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: 'bg-slate-100 text-slate-700 border border-slate-300',
  emerald: 'bg-emerald-50 text-emerald-800 border border-emerald-300',
  amber: 'bg-amber-50 text-amber-900 border border-amber-300',
  rose: 'bg-rose-50 text-rose-900 border border-rose-300',
  slate: 'bg-slate-100 text-slate-800 border border-slate-300',
  zinc: 'bg-zinc-100 text-zinc-700 border border-zinc-300',
  sky: 'bg-sky-50 text-sky-800 border border-sky-300',
  violet: 'bg-violet-50 text-violet-800 border border-violet-300',
};

export function Badge({ tone = 'neutral', children, className = '', title }: BadgeProps): JSX.Element {
  return (
    <span
      title={title}
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        TONE_CLASSES[tone],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </span>
  );
}

export default Badge;
