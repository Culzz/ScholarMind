import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ClaimChip } from '@/components/ClaimChip';
import { claimStateMeta } from '@/lib/claims';

describe('ClaimChip', () => {
  it('always renders the text label, not only a colour', () => {
    render(<ClaimChip state="needs_verification" />);
    expect(screen.getByText('Needs verification')).toBeInTheDocument();
  });

  it('renders every claim state with a distinct label', () => {
    const states = [
      'confirmed',
      'not_established',
      'needs_verification',
      'stale',
      'expired',
    ] as const;

    for (const state of states) {
      const meta = claimStateMeta(state);
      const { unmount, getByText } = render(<ClaimChip state={state} />);
      expect(getByText(meta.label)).toBeInTheDocument();
      unmount();
    }
  });

  it('falls back safely for an unknown state', () => {
    render(<ClaimChip state={'nonsense' as never} />);
    expect(screen.getByText('Not established')).toBeInTheDocument();
  });
});
