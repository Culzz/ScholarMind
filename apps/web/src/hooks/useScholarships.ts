import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import type { Paginated, ScholarshipFilters, ScholarshipListItem } from '@/types/api';

export const SCHOLARSHIP_PAGE_SIZE = 25;

/** Convert the UI filter object into API query parameters. */
export function filtersToQuery(filters: ScholarshipFilters): Record<string, string | number | undefined> {
  const query: Record<string, string | number | undefined> = {};
  if (filters.q) query.q = filters.q;
  if (filters.nationality) query.nationality = filters.nationality;
  if (filters.level) query.level = filters.level;
  if (filters.field) query.field = filters.field;
  if (filters.destination) query.destination = filters.destination;
  if (filters.funding_component) query.funding_component = filters.funding_component;
  if (filters.cycle_year) query.cycle_year = filters.cycle_year;
  if (filters.verification) query.verification = filters.verification;
  if (filters.deadline_window) query.deadline_window = filters.deadline_window;
  if (filters.sort) query.sort = filters.sort;
  if (filters.cursor) query.cursor = filters.cursor;
  query.limit = filters.limit ?? SCHOLARSHIP_PAGE_SIZE;
  return query;
}

/**
 * FR-1: paginated, filterable scholarship list.
 */
export function useScholarships(
  filters: ScholarshipFilters,
): UseQueryResult<Paginated<ScholarshipListItem>, Error> {
  return useQuery<Paginated<ScholarshipListItem>, Error>({
    queryKey: ['scholarships', filters],
    queryFn: ({ signal }) =>
      apiGet<Paginated<ScholarshipListItem>>('/scholarships', {
        query: filtersToQuery(filters),
        signal,
      }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}
