import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import type { RecommendationResponse } from '@/types/api';

/**
 * FR-9: explainable personalised ranking. The score is a prioritisation aid —
 * never a probability of admission. Every factor and its weight is returned so
 * the ordering can be audited.
 */
export function useRecommendations(): UseQueryResult<RecommendationResponse, Error> {
  return useQuery<RecommendationResponse, Error>({
    queryKey: ['recommendations'],
    queryFn: ({ signal }) => apiGet<RecommendationResponse>('/recommendations', { signal }),
    staleTime: 300_000,
  });
}
