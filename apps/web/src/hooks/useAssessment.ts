import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { apiPost } from '@/lib/api';
import type { EvaluateRequest, EvaluateResponse } from '@/types/api';

/**
 * FR-3: run the deterministic rule engine for a profile against one or more
 * cycles. The response carries per-rule verdicts, counts and the list of
 * profile fields that would resolve open unknowns.
 */
export function useEvaluateEligibility(): UseMutationResult<EvaluateResponse, Error, EvaluateRequest> {
  const queryClient = useQueryClient();
  return useMutation<EvaluateResponse, Error, EvaluateRequest>({
    mutationFn: (request) => apiPost<EvaluateResponse>('/eligibility/evaluate', request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['assessments'] });
      void queryClient.invalidateQueries({ queryKey: ['recommendations'] });
    },
  });
}

export interface ExplainResponse {
  assessment_id: string;
  /** Human-readable reasoning trace, one entry per rule. */
  trace: Array<{
    rule_id: string;
    rule_text: string;
    verdict: string;
    reason: string;
    evidence_ids: string[];
  }>;
  summary?: string;
}

/**
 * Human-readable reasoning trace for a stored assessment (FR-3.6).
 */
export function useExplainAssessment(
  assessmentId: string | undefined,
): UseQueryResult<ExplainResponse, Error> {
  return useQuery<ExplainResponse, Error>({
    queryKey: ['assessments', 'explain', assessmentId],
    queryFn: ({ signal }) =>
      apiPost<ExplainResponse>('/eligibility/explain', { assessment_id: assessmentId }),
    enabled: Boolean(assessmentId),
    staleTime: 300_000,
  });
}
