import { useCallback, useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  /** Set to false for destructive confirmations that should not be dismissable by backdrop click. */
  dismissOnBackdrop?: boolean;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  dismissOnBackdrop = true,
}: DialogProps): JSX.Element | null {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const container = dialogRef.current;
      if (!container) return;
      const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (element) => element.offsetParent !== null || element === document.activeElement,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === container)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return undefined;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const container = dialogRef.current;
    const focusable = container?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (focusable ?? container)?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div
        className="absolute inset-0 bg-slate-900/50"
        aria-hidden="true"
        onClick={dismissOnBackdrop ? onClose : undefined}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="relative z-10 max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-slate-200 bg-white p-5 shadow-xl animate-fade-in"
      >
        <header className="mb-3">
          <h2 id={titleId} className="text-lg font-semibold text-slate-900">
            {title}
          </h2>
          {description ? (
            <p id={descriptionId} className="mt-1 text-sm text-slate-600">
              {description}
            </p>
          ) : null}
        </header>
        <div className="text-sm text-slate-700">{children}</div>
        {footer ? <footer className="mt-5 flex flex-wrap justify-end gap-2">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}

export default Dialog;
