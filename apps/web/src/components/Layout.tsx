import { Suspense, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
  description: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', end: true, description: 'What needs attention today' },
  { to: '/discover', label: 'Discover', description: 'Search and filter opportunities' },
  { to: '/eligibility', label: 'Eligibility', description: 'Rule-by-rule verdicts' },
  { to: '/compare', label: 'Compare', description: 'Side-by-side comparison' },
  { to: '/planner', label: 'Planner', description: 'Application plan and tasks' },
  { to: '/assistant', label: 'Assistant', description: 'Evidence-grounded answers' },
  { to: '/settings', label: 'Settings', description: 'Profile and controls' },
];

function navClasses({ isActive }: { isActive: boolean }): string {
  return [
    'block rounded-md px-3 py-2 text-sm font-medium transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2',
    isActive
      ? 'bg-sky-600 text-white shadow-sm'
      : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900',
  ].join(' ');
}

function PageFallback(): JSX.Element {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <span className="sr-only">Loading page…</span>
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-40 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    </div>
  );
}

export function Layout(): JSX.Element {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { user, isAuthenticated, signOut } = useAuth();

  const nav = (
    <nav aria-label="Primary" className="space-y-1">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={navClasses}
          onClick={() => setMobileNavOpen(false)}
        >
          <span className="block">{item.label}</span>
          <span className="block text-xs font-normal opacity-80">{item.description}</span>
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-full bg-slate-50 text-slate-900">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              className="md:hidden"
              aria-label={mobileNavOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={mobileNavOpen}
              aria-controls="primary-navigation"
              onClick={() => setMobileNavOpen((open) => !open)}
            >
              <span aria-hidden="true">☰</span>
            </Button>
            <div>
              <p className="text-base font-semibold tracking-tight">ScholarMind</p>
              <p className="text-xs text-slate-600">
                Source-grounded scholarship intelligence for African students
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <p className="hidden text-sm text-slate-600 sm:block">
              {isAuthenticated && user ? user.email : 'Browsing anonymously'}
            </p>
            {isAuthenticated ? (
              <Button variant="secondary" size="sm" onClick={() => void signOut()}>
                Sign out
              </Button>
            ) : (
              <NavLink
                to="/settings"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
              >
                Sign in
              </NavLink>
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6 sm:px-6">
        <aside
          id="primary-navigation"
          className={`${
            mobileNavOpen ? 'block' : 'hidden'
          } fixed inset-x-0 top-[57px] z-20 max-h-[70vh] overflow-y-auto border-b border-slate-200 bg-white px-4 py-4 md:static md:block md:max-h-none md:w-60 md:shrink-0 md:overflow-visible md:border-0 md:bg-transparent md:px-0 md:py-0`}
        >
          {nav}
          <p className="mt-6 rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-600">
            Every material fact shows its claim state. Colour is never the only signal — read the label.
          </p>
        </aside>

        <main id="main-content" className="min-w-0 flex-1">
          <Suspense fallback={<PageFallback />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default Layout;
