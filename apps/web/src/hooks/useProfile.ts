import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { apiGet, apiPut } from '@/lib/api';
import type { Profile, ProfileInput } from '@/types/api';

/**
 * The signed-in student's profile. A missing field is never coerced into a
 * "satisfied" rule — the eligibility engine reads these values verbatim.
 */
export function useProfile(): UseQueryResult<Profile, Error> {
  return useQuery<Profile, Error>({
    queryKey: ['profile'],
    queryFn: ({ signal }) => apiGet<Profile>('/profile', { signal }),
    staleTime: 30_000,
    retry: false,
  });
}

export function useUpdateProfile(): UseMutationResult<Profile, Error, ProfileInput> {
  const queryClient = useQueryClient();
  return useMutation<Profile, Error, ProfileInput>({
    mutationFn: (input) => apiPut<Profile>('/profile', input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['profile'] });
      void queryClient.invalidateQueries({ queryKey: ['assessments'] });
      void queryClient.invalidateQueries({ queryKey: ['recommendations'] });
    },
  });
}
