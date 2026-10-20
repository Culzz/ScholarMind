import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { apiDelete } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useProfile } from '@/hooks/useProfile';
import { formatDateTime } from '@/lib/format';
import { CLAIM_STATES, claimStateMeta } from '@/lib/claims';

const ALERT_TYPES = [
  { id: 'deadline', label: 'Cycle closing reminders' },
  { id: 'cycle_opening', label: 'Cycle opening announcements' },
  { id: 'source_change', label: 'Changes to saved scholarships' },
  { id: 'task_due', label: 'Task due reminders' },
];

const TRUST_TIER_OPTIONS = [
  { id: 'official_primary', label: 'Official — primary funder' },
  { id: 'official_secondary', label: 'Official — secondary' },
  { id: 'partner', label: 'Partner' },
  { id: 'aggregator', label: 'Aggregator' },
];

/**
 * Settings: profile, notifications, data export, account deletion and the
 * claim states the student wants to see emphasized.
 */
export function SettingsPage(): JSX.Element {
  const { user, isAuthenticated, signOut } = useAuth();
  const profileQuery = useProfile();
  const toast = useToast();

  const [alerts, setAlerts] = useState<string[]>(['deadline', 'task_due']);
  const [trustTiers, setTrustTiers] = useState<string[]>(['official_primary', 'official_secondary']);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const toggle = (list: string[], id: string): string[] =>
    list.includes(id) ? list.filter((entry) => entry !== id) : [...list, id];

  const exportProfile = (): void => {
    if (!profileQuery.data) return;
    const blob = new Blob([JSON.stringify(profileQuery.data, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'scholarmind-profile.json';
    link.click();
    URL.revokeObjectURL(url);
    toast.push({ title: 'Export ready', description: 'Your profile was downloaded as JSON.', tone: 'success' });
  };

  const handleDelete = async (): Promise<void> => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await apiDelete('/account');
      setDeleteDialogOpen(false);
      await signOut();
      toast.push({ title: 'Account deleted', tone: 'success' });
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : 'We could not delete your account.');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Settings</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Control your profile, the reminders you receive, and the data we hold about you.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Account">
          {isAuthenticated && user ? (
            <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="font-medium text-slate-700">Email</dt>
                <dd className="text-slate-600">{user.email}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-700">Role</dt>
                <dd className="text-slate-600">{user.role}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-700">Verified</dt>
                <dd className="text-slate-600">{user.email_verified ? 'Yes' : 'Not yet'}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-slate-700">
              You are browsing anonymously. Sign in to save scholarships, run eligibility checks and
              build a plan.
            </p>
          )}

          {profileQuery.isLoading ? <Skeleton className="mt-3 h-16 w-full" /> : null}

          {profileQuery.data ? (
            <p className="mt-3 text-sm text-slate-700">
              Profile last updated {formatDateTime(profileQuery.data.updated_at ?? null)}.{' '}
              <Link
                to="/eligibility"
                className="font-medium text-sky-700 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2"
              >
                Edit your profile
              </Link>
            </p>
          ) : null}
        </Card>

        <Card title="Notifications" description="Opt in to the reminders you want. We never send them by default.">
          <fieldset>
            <legend className="sr-only">Notification preferences</legend>
            <ul className="space-y-2">
              {ALERT_TYPES.map((alert) => (
                <li key={alert.id}>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-2 focus:ring-sky-500"
                      checked={alerts.includes(alert.id)}
                      onChange={() => setAlerts((current) => toggle(current, alert.id))}
                    />
                    {alert.label}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
          <p className="mt-3 text-xs text-slate-600">
            Preferences apply to this session. Sign-in is required to sync them to your account.
          </p>
        </Card>

        <Card title="Source trust preferences" description="Which sources you want us to prioritise.">
          <fieldset>
            <legend className="sr-only">Trust tier preferences</legend>
            <ul className="space-y-2">
              {TRUST_TIER_OPTIONS.map((tier) => (
                <li key={tier.id}>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-2 focus:ring-sky-500"
                      checked={trustTiers.includes(tier.id)}
                      onChange={() => setTrustTiers((current) => toggle(current, tier.id))}
                    />
                    {tier.label}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>

          <div className="mt-4 border-t border-slate-200 pt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              Claim states you can see
            </h3>
            <ul className="mt-1 space-y-1 text-sm text-slate-700">
              {CLAIM_STATES.map((state) => (
                <li key={state}>
                  <span className="font-medium text-slate-900">{claimStateMeta(state).label}</span> —{' '}
                  {claimStateMeta(state).description}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-600">
              All states are always visible. This list is a reminder of what each one means, not a
              filter — colour is never the only signal.
            </p>
          </div>
        </Card>

        <Card title="Your data">
          <p className="text-sm text-slate-700">
            Download everything we hold about your profile, or delete your account and personal data
            permanently.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={exportProfile}
              disabled={!profileQuery.data}
            >
              Export my profile
            </Button>
            <Button variant="danger" onClick={() => setDeleteDialogOpen(true)}>
              Delete my account
            </Button>
          </div>
          {profileQuery.isError ? (
            <div className="mt-3">
              <ErrorState
                title="Could not load your profile"
                message={profileQuery.error instanceof Error ? profileQuery.error.message : undefined}
                onRetry={() => void profileQuery.refetch()}
              />
            </div>
          ) : null}
        </Card>
      </div>

      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        title="Delete your account?"
        description="This permanently removes your profile, saved scholarships, applications and answer history."
        dismissOnBackdrop={false}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteDialogOpen(false)}>
              Keep my account
            </Button>
            <Button variant="danger" loading={deleting} onClick={() => void handleDelete()}>
              Delete permanently
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-700">
          Public scholarship records and official-source snapshots are not affected — they are public
          information.
        </p>
        {deleteError ? (
          <div className="mt-3">
            <ErrorState title="Deletion failed" message={deleteError} />
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}

export default SettingsPage;
