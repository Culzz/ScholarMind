import { useMutation, type UseMutationResult } from '@tanstack/react-query';

import { apiPost } from '@/lib/api';
import type { AskRequest, AssistantAnswer } from '@/types/api';

/**
 * FR-6: ask the grounded assistant. The response always carries the answer,
 * the claim list, cited evidence, conflicts, freshness warnings and — when the
 * evidence was insufficient — an explicit abstention with the missing facts.
 */
export function useAsk(): UseMutationResult<AssistantAnswer, Error, AskRequest> {
  return useMutation<AssistantAnswer, Error, AskRequest>({
    mutationFn: (request) => apiPost<AssistantAnswer>('/assistant/ask', request),
  });
}
