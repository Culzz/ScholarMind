export interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = 'h-4 w-full' }: SkeletonProps): JSX.Element {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-slate-200 ${className}`} />;
}

export interface SkeletonTextProps {
  lines?: number;
  className?: string;
}

export function SkeletonText({ lines = 3, className = '' }: SkeletonTextProps): JSX.Element {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: Math.max(1, lines) }).map((_, index) => (
        <Skeleton key={index} className={index === 0 ? 'h-4 w-3/4' : 'h-4 w-full'} />
      ))}
    </div>
  );
}

export interface SkeletonCardProps {
  title?: boolean;
  lines?: number;
}

export function SkeletonCard({ title = true, lines = 3 }: SkeletonCardProps): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {title ? <Skeleton className="mb-3 h-5 w-1/3" /> : null}
      <SkeletonText lines={lines} />
    </div>
  );
}

export default Skeleton;
