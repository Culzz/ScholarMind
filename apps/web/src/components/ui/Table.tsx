import type { ReactNode } from 'react';

export interface TableColumn<T> {
  /** Stable key, also used as the accessible header association. */
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  headerClassName?: string;
  cellClassName?: string;
}

export interface TableProps<T> {
  caption: string;
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyMessage?: string;
  className?: string;
}

export function Table<T>({
  caption,
  columns,
  rows,
  rowKey,
  emptyMessage = 'Nothing to show yet.',
  className = '',
}: TableProps<T>): JSX.Element {
  if (rows.length === 0) {
    return (
      <div className={className}>
        <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
          {emptyMessage}
        </p>
      </div>
    );
  }

  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-slate-50">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600 ${column.headerClassName ?? ''}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((row) => (
            <tr key={rowKey(row)} className="align-top hover:bg-slate-50">
              {columns.map((column) => (
                <td key={column.key} className={`px-3 py-3 text-slate-700 ${column.cellClassName ?? ''}`}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default Table;
