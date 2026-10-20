import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** Icon-only buttons must provide an `aria-label`. */
  iconOnly?: boolean;
  children?: ReactNode;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    'bg-sky-600 text-white hover:bg-sky-700 active:bg-sky-800 disabled:bg-sky-300 shadow-sm',
  secondary:
    'bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 active:bg-slate-100 disabled:text-slate-400',
  ghost: 'bg-transparent text-slate-700 hover:bg-slate-100 active:bg-slate-200 disabled:text-slate-400',
  danger:
    'bg-rose-600 text-white hover:bg-rose-700 active:bg-rose-800 disabled:bg-rose-300 shadow-sm',
  link: 'bg-transparent text-sky-700 underline underline-offset-4 hover:text-sky-900 disabled:text-slate-400',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs gap-1.5',
  md: 'px-3.5 py-2 text-sm gap-2',
  lg: 'px-5 py-2.5 text-base gap-2',
};

const ICON_SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'h-7 w-7',
  md: 'h-9 w-9',
  lg: 'h-11 w-11',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  iconOnly = false,
  className = '',
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps): JSX.Element {
  const sizeClasses = iconOnly ? ICON_SIZE_CLASSES[size] : SIZE_CLASSES[size];
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        'inline-flex items-center justify-center rounded-md font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed',
        VARIANT_CLASSES[variant],
        sizeClasses,
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : null}
      {children}
    </button>
  );
}

export default Button;
