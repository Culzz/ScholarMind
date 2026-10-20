export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  message = 'We could not load this data. The figures below may be out of date — retry when you can.',
  onRetry,
  retryLabel = 'Try again',
}: ErrorStateProps): JSX.Element {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-2 rounded-lg border border-rose-300 bg-rose-50 px-4 py-4 text-sm text-rose-900"
    >
      <p className="font-semibold">{title}</p>
      <p className="text-rose-800">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-800 hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600 focus-visible:ring-offset-2"
        >
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

export default ErrorState;
