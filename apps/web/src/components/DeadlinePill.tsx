import { ClaimChip } from '@/components/ClaimChip';
import { formatDate, formatRelativeDeadline } from '@/lib/format';
import type { ClaimState, ScholarshipCycle } from '@/types/api';

export interface DeadlinePillProps {
  deadline: string | null;
  /** The claim state of the deadline fact (e.g. `needs_verification`). */
  claimState?: ClaimState;
  /** Raw wording as published by the source, shown when it differs from the date. */
  rawText?: string | null;
  timezone?: string | null;
  label?: string;
}

const TONE_CLASSES: Record<string, string | undefined> = {
  urgent: 'border-rose-300 bg-rose-50 text-rose-900',
  soon: 'border-amber-300 bg-amber-50 text-amber-900',
  open: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  past: 'border-zinc-300 bg-zinc-100 text-zinc-700',
  unknown: 'border-slate-300 bg-slate-100 text-slate-700',
};

/**
 * A deadline with both the absolute date and the relative hint. When the source
 * wording is imprecise, the raw text is shown next to the parsed date so the
 * reader can judge the precision themselves.
 */
export function DeadlinePill({
  deadline,
  claimState,
  rawText,
  timezone,
  label = 'Deadline',
}: DeadlinePillProps): JSX.Element {
  const relative = formatRelativeDeadline(deadline);
  const toneClass = TONE_CLASSES[relative.tone] ?? TONE_CLASSES.unknown ?? '';
  const showRaw = Boolean(rawText && rawText.trim() && rawText.trim() !== formatDate(deadline));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${toneClass}`}
      >
        <span className="font-semibold">{label}:</span>
        <span>{formatDate(deadline)}</span>
        <span aria-hidden="true">·</span>
        <span>{relative.label}</span>
      </span>
      {claimState ? <ClaimChip state={claimState} size="sm" /> : null}
      {showRaw ? (
        <span className="text-xs text-slate-600">
          Source wording: <span className="italic">“{rawText}”</span>
          {timezone ? ` (${timezone})` : ''}
        </span>
      ) : null}
    </div>
  );
}

export interface CycleDeadlinePillProps {
  cycle: Pick<ScholarshipCycle, 'deadline_at' | 'deadline_raw_text' | 'deadline_timezone' | 'claim_state'>;
}

export function CycleDeadlinePill({ cycle }: CycleDeadlinePillProps): JSX.Element {
  return (
    <DeadlinePill
      deadline={cycle.deadline_at}
      claimState={cycle.claim_state}
      rawText={cycle.deadline_raw_text}
      timezone={cycle.deadline_timezone}
    />
  );
}

export default DeadlinePill;
