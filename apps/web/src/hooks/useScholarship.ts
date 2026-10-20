import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import type { ChangeHistoryResponse, ScholarshipDetail } from '@/types/api';

/**
 * FR-2: scholarship detail — cycles, funding components, sources, rules and the
 * latest eligibility assessment for the signed-in profile.
 */
export function useScholarship(id: string | undefined): UseQueryResult<ScholarshipDetail, Error> {
  return useQuery<ScholarshipDetail, Error>({
    queryKey: ['scholarship', id],
    queryFn: ({ signal }) => apiGet<ScholarshipDetail>(`/scholarships/${id ?? ''}`, { signal }),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/**
 * FR-2.4 / FR-4: change history and unresolved conflicts for a scholarship.
 */
export function useChangeHistory(
  id: string | undefined,
): UseQueryResult<ChangeHistoryResponse, Error> {
  return useQuery<ChangeHistoryResponse, Error>({
    queryKey: ['scholarship', id, 'history'],
    queryFn: ({ signal }) =>
      apiGet<ChangeHistoryResponse>(`/scholarships/${id ?? ''}/history`, { signal }),
    enabled: Boolean(id),
    staleTime: 120_000,
  });
}
