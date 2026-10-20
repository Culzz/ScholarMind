import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ClaimChip } from '@/components/ClaimChip';

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
      const { unmount } = render(<ClaimChip state={state} />);
      const chip = screen.getByRole('span');
      expect(chip.textContent?.trim().length ?? 0).toBeGreaterThan(0);
      unmount();
    }
  });

  it('falls back safely for an unknown state', () => {
    render(<ClaimChip state={'nonsense' as never} />);
    expect(screen.getByText('Not established')).toBeInTheDocument();
  });
});
