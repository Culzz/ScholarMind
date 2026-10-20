import type { FormEvent } from 'react';

import { Button } from '@/components/ui/Button';
import {
  COUNTRY_OPTIONS,
  DEADLINE_WINDOW_OPTIONS,
  DEGREE_LEVEL_OPTIONS,
  FIELD_OPTIONS,
  FUNDING_COMPONENT_OPTIONS,
  SORT_OPTIONS,
} from '@/lib/countries';
import { CLAIM_STATES, claimStateMeta } from '@/lib/claims';
import type { ScholarshipFilters } from '@/types/api';

export interface FilterPanelProps {
  filters: ScholarshipFilters;
  onChange: (filters: ScholarshipFilters) => void;
  onReset: () => void;
  resultCount?: number | null;
}

const selectClass =
  'block w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/40';

function Label({ htmlFor, children }: { htmlFor: string; children: string }): JSX.Element {
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
      {children}
    </label>
  );
}

/**
 * FR-1.2: typed filters. The panel is controlled so the query key (and
 * therefore the request) always matches what is on screen.
 */
export function FilterPanel({
  filters,
  onChange,
  onReset,
  resultCount,
}: FilterPanelProps): JSX.Element {
  const update = (patch: Partial<ScholarshipFilters>): void => {
    onChange({ ...filters, ...patch, cursor: null });
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    update({});
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Scholarship filters"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Filters</h2>
        <Button type="button" variant="ghost" size="sm" onClick={onReset}>
          Reset
        </Button>
      </div>

      <div className="mt-3 space-y-3">
        <div>
          <Label htmlFor="filter-q">Keyword</Label>
          <input
            id="filter-q"
            type="search"
            value={filters.q ?? ''}
            onChange={(event) => update({ q: event.target.value })}
            placeholder="Scholarship, funder, field…"
            className={selectClass}
          />
        </div>

        <div>
          <Label htmlFor="filter-nationality">Nationality eligibility</Label>
          <select
            id="filter-nationality"
            value={filters.nationality ?? ''}
            onChange={(event) => update({ nationality: event.target.value })}
            className={selectClass}
          >
            <option value="">Any nationality</option>
            {COUNTRY_OPTIONS.map((country) => (
              <option key={country.iso3} value={country.iso3}>
                {country.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-level">Degree level</Label>
          <select
            id="filter-level"
            value={filters.level ?? ''}
            onChange={(event) => update({ level: event.target.value })}
            className={selectClass}
          >
            <option value="">Any level</option>
            {DEGREE_LEVEL_OPTIONS.map((level) => (
              <option key={level.value} value={level.value}>
                {level.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-field">Field of study</Label>
          <select
            id="filter-field"
            value={filters.field ?? ''}
            onChange={(event) => update({ field: event.target.value })}
            className={selectClass}
          >
            <option value="">Any field</option>
            {FIELD_OPTIONS.map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-destination">Destination</Label>
          <select
            id="filter-destination"
            value={filters.destination ?? ''}
            onChange={(event) => update({ destination: event.target.value })}
            className={selectClass}
          >
            <option value="">Any destination</option>
            {COUNTRY_OPTIONS.map((country) => (
              <option key={country.iso3} value={country.iso3}>
                {country.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-funding">Funding component</Label>
          <select
            id="filter-funding"
            value={filters.funding_component ?? ''}
            onChange={(event) => update({ funding_component: event.target.value })}
            className={selectClass}
          >
            <option value="">Any component</option>
            {FUNDING_COMPONENT_OPTIONS.map((component) => (
              <option key={component.value} value={component.value}>
                {component.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-cycle-year">Intake year</Label>
          <input
            id="filter-cycle-year"
            type="number"
            min={2000}
            max={2100}
            value={filters.cycle_year ?? ''}
            onChange={(event) =>
              update({ cycle_year: event.target.value ? Number(event.target.value) : undefined })
            }
            placeholder="2027"
            className={selectClass}
          />
        </div>

        <div>
          <Label htmlFor="filter-verification">Verification status</Label>
          <select
            id="filter-verification"
            value={filters.verification ?? ''}
            onChange={(event) =>
              update({ verification: event.target.value as ScholarshipFilters['verification'] })
            }
            className={selectClass}
          >
            <option value="">Any status</option>
            {CLAIM_STATES.map((state) => (
              <option key={state} value={state}>
                {claimStateMeta(state).label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-deadline">Deadline window</Label>
          <select
            id="filter-deadline"
            value={filters.deadline_window ?? ''}
            onChange={(event) => update({ deadline_window: event.target.value })}
            className={selectClass}
          >
            <option value="">Any deadline</option>
            {DEADLINE_WINDOW_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <Label htmlFor="filter-sort">Sort by</Label>
          <select
            id="filter-sort"
            value={filters.sort ?? 'deadline'}
            onChange={(event) =>
              update({ sort: event.target.value as ScholarshipFilters['sort'] })
            }
            className={selectClass}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-600" aria-live="polite">
        {resultCount === null || resultCount === undefined
          ? 'Filters apply to the current results.'
          : `${resultCount} result${resultCount === 1 ? '' : 's'} match the current filters.`}
      </p>
    </form>
  );
}

export default FilterPanel;
