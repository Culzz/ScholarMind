import type { HTMLAttributes, ReactNode } from 'react';

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  children?: ReactNode;
  /** Optional heading rendered inside the card body. */
  title?: ReactNode;
  description?: ReactNode;
  /** Rendered in the top-right of the card header. */
  actions?: ReactNode;
  footer?: ReactNode;
}

export function Card({
  children,
  title,
  description,
  actions,
  footer,
  className = '',
  ...rest
}: CardProps): JSX.Element {
  const hasHeader = Boolean(title || description || actions);
  return (
    <section
      className={[
        'rounded-lg border border-slate-200 bg-white shadow-sm',
        'focus-within:ring-2 focus-within:ring-sky-200',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...rest}
    >
      {hasHeader ? (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div className="min-w-0">
            {title ? <h2 className="text-base font-semibold text-slate-900">{title}</h2> : null}
            {description ? <p className="mt-1 text-sm text-slate-600">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className="px-4 py-4 sm:px-5">{children}</div>
      {footer ? (
        <footer className="border-t border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 sm:px-5">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}

export function CardTitle({ children, className = '' }: { children: ReactNode; className?: string }): JSX.Element {
  return <h3 className={`text-sm font-semibold text-slate-900 ${className}`}>{children}</h3>;
}

export function CardBody({ children, className = '' }: { children: ReactNode; className?: string }): JSX.Element {
  return <div className={`text-sm text-slate-700 ${className}`}>{children}</div>;
}

export function CardFooter({ children, className = '' }: { children: ReactNode; className?: string }): JSX.Element {
  return <div className={`text-sm text-slate-600 ${className}`}>{children}</div>;
}

export default Card;
