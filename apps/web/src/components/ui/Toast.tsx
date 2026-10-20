import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type ToastTone = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
}

export interface ToastContextValue {
  push: (toast: { title: string; description?: string; tone?: ToastTone }) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_CLASSES: Record<ToastTone, string> = {
  info: 'border-sky-300 bg-sky-50 text-sky-900',
  success: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  warning: 'border-amber-300 bg-amber-50 text-amber-900',
  error: 'border-rose-300 bg-rose-50 text-rose-900',
};

export function ToastProvider({ children }: { children: ReactNode }): JSX.Element {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback<ToastContextValue['push']>(
    (toast) => {
      counter.current += 1;
      const id = `toast-${counter.current}`;
      setToasts((current) => [...current, { id, tone: 'info', ...toast }]);
      window.setTimeout(() => dismiss(id), 6000);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={`pointer-events-auto rounded-md border px-3 py-2 text-sm shadow-lg ${TONE_CLASSES[toast.tone]}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{toast.title}</p>
                {toast.description ? <p className="mt-0.5 text-xs">{toast.description}</p> : null}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss notification"
                className="rounded p-0.5 text-xs font-bold hover:bg-white/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used inside a <ToastProvider>.');
  }
  return context;
}

export default ToastProvider;
