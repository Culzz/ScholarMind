import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

export interface TabItem {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  /** Controlled active tab id. */
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
  label: string;
  className?: string;
}

export function Tabs({
  items,
  value,
  defaultValue,
  onChange,
  label,
  className = '',
}: TabsProps): JSX.Element {
  const baseId = useId();
  const [internal, setInternal] = useState<string>(defaultValue ?? items[0]?.id ?? '');
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const active = value ?? internal;

  const select = (id: string): void => {
    if (value === undefined) setInternal(id);
    onChange?.(id);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number): void => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const lastIndex = items.length - 1;
    let nextIndex = index;
    if (event.key === 'ArrowRight') nextIndex = index === lastIndex ? 0 : index + 1;
    if (event.key === 'ArrowLeft') nextIndex = index === 0 ? lastIndex : index - 1;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = lastIndex;
    const next = items[nextIndex];
    if (!next) return;
    select(next.id);
    buttonRefs.current[nextIndex]?.focus();
  };

  if (items.length === 0) {
    return <p className="text-sm text-slate-600">No sections to show.</p>;
  }

  return (
    <div className={className}>
      <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-slate-200">
        {items.map((item, index) => {
          const selected = item.id === active;
          return (
            <button
              key={item.id}
              ref={(element) => {
                buttonRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              aria-controls={`${baseId}-panel-${item.id}`}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              onClick={() => select(item.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={[
                '-mb-px rounded-t-md border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-1',
                selected
                  ? 'border-sky-600 text-sky-700'
                  : 'border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900',
              ].join(' ')}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) => (
        <div
          key={item.id}
          role="tabpanel"
          id={`${baseId}-panel-${item.id}`}
          aria-labelledby={`${baseId}-tab-${item.id}`}
          hidden={item.id !== active}
          tabIndex={0}
          className="pt-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-200"
        >
          {item.id === active ? item.content : null}
        </div>
      ))}
    </div>
  );
}

export default Tabs;
