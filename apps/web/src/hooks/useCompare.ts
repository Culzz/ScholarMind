import { useMutation, type UseMutationResult } from '@tanstack/react-query';

import { apiPost } from '@/lib/api';
import type { CompareRequest, CompareResponse } from '@/types/api';

/**
 * FR-7: side-by-side comparison of 2–5 scholarships.
 */
export function useCompare(): UseMutationResult<CompareResponse, Error, CompareRequest> {
  return useMutation<CompareResponse, Error, CompareRequest>({
    mutationFn: (request) => apiPost<CompareResponse>('/compare', request),
  });
}
