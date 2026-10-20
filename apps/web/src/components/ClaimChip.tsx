import { claimStateMeta } from '@/lib/claims';
import type { ClaimState } from '@/types/api';

export interface ClaimChipProps {
  state: ClaimState | string | null | undefined;
  /** Override the label shown next to the colour (still text, never colour only). */
  label?: string;
  size?: 'sm' | 'md';
  className?: string;
}

/**
 * Renders a claim state as a coloured chip **with** its text label.
 * The label is always present — colour is never the only signal.
 */
export function ClaimChip({ state, label, size = 'md', className = '' }: ClaimChipProps): JSX.Element {
  const meta = claimStateMeta(state);
  const text = label ?? meta.label;
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
        meta.chipClass,
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      title={meta.description}
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${meta.dotClass}`} />
      <span>{text}</span>
    </span>
  );
}

export default ClaimChip;
