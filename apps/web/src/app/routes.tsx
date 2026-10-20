import { lazy } from 'react';
import { createBrowserRouter, Link, type RouteObject } from 'react-router-dom';

import Layout from '@/components/Layout';

/**
 * Route table.
 *
 * Every page is lazy loaded so the first paint only carries the shell. The
 * shared layout wraps the pages and provides the Suspense boundary.
 */
const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'));
const DiscoveryPage = lazy(() => import('@/features/discovery/DiscoveryPage'));
const ScholarshipDetailPage = lazy(
  () => import('@/features/scholarship-details/ScholarshipDetailPage'),
);
const EligibilityPage = lazy(() => import('@/features/eligibility/EligibilityPage'));
const ComparePage = lazy(() => import('@/features/compare/ComparePage'));
const PlannerPage = lazy(() => import('@/features/planner/PlannerPage'));
const AssistantPage = lazy(() => import('@/features/assistant/AssistantPage'));
const SettingsPage = lazy(() => import('@/features/settings/SettingsPage'));

function NotFound(): JSX.Element {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <h1 className="text-xl font-semibold text-slate-900">Page not found</h1>
      <p className="mt-2 text-sm text-slate-600">
        That page does not exist. Everything in ScholarMind starts from the dashboard.
      </p>
      <Link
        to="/"
        className="mt-4 inline-flex items-center rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
      >
        Back to the dashboard
      </Link>
    </div>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'discover', element: <DiscoveryPage /> },
      { path: 'scholarships/:id', element: <ScholarshipDetailPage /> },
      { path: 'eligibility', element: <EligibilityPage /> },
      { path: 'compare', element: <ComparePage /> },
      { path: 'planner', element: <PlannerPage /> },
      { path: 'assistant', element: <AssistantPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);

export default routes;
