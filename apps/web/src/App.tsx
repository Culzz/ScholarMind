import { useMemo } from 'react';
import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ToastProvider } from '@/components/ui/Toast';
import { AuthProvider } from '@/lib/auth';
import { router } from '@/app/routes';

/**
 * The application shell: data layer, notifications, authentication and routing.
 */
export function App(): JSX.Element {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 30_000,
          },
          mutations: {
            retry: 0,
          },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
