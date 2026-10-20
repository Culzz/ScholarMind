import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost } from '@/lib/api';
import type {
  Application,
  ApplicationTask,
  CreateApplicationRequest,
  Paginated,
  UpdateTaskRequest,
} from '@/types/api';

/** FR-8.2: the student's application plans. */
export function useApplications(): UseQueryResult<Paginated<Application>, Error> {
  return useQuery<Paginated<Application>, Error>({
    queryKey: ['applications'],
    queryFn: ({ signal }) => apiGet<Paginated<Application>>('/applications', { signal }),
    staleTime: 30_000,
  });
}

/** FR-8.2: create a plan targeting a specific cycle. */
export function useCreateApplication(): UseMutationResult<
  Application,
  Error,
  CreateApplicationRequest
> {
  const queryClient = useQueryClient();
  return useMutation<Application, Error, CreateApplicationRequest>({
    mutationFn: (request) => apiPost<Application>('/applications', request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['applications'] });
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });
}

/** FR-8.4: the task checklist, optionally scoped to one application. */
export function useTasks(
  applicationId?: string,
): UseQueryResult<Paginated<ApplicationTask>, Error> {
  return useQuery<Paginated<ApplicationTask>, Error>({
    queryKey: ['tasks', applicationId ?? 'all'],
    queryFn: ({ signal }) =>
      apiGet<Paginated<ApplicationTask>>('/tasks', {
        query: applicationId ? { application_id: applicationId } : undefined,
        signal,
      }),
    staleTime: 30_000,
  });
}

/** FR-8.4: update a task (status, due date, notes). */
export function useUpdateTask(): UseMutationResult<
  ApplicationTask,
  Error,
  { id: string } & UpdateTaskRequest
> {
  const queryClient = useQueryClient();
  return useMutation<ApplicationTask, Error, { id: string } & UpdateTaskRequest>({
    mutationFn: ({ id, ...update }) =>
      apiPatch<ApplicationTask>(`/tasks/${id}`, update),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      void queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}
