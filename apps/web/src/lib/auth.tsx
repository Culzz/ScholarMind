/**
 * Authentication context.
 *
 * Security notes
 * --------------
 * - The access token lives in a module-scoped variable inside `lib/api.ts`
 *   (i.e. in memory only). It is never written to `localStorage` or
 *   `sessionStorage`, so a script injected into the page cannot read it back
 *   after the tab is closed, and it never leaves the app in a persisted store.
 * - Session continuity across reloads relies on the API's **httpOnly** refresh
 *   cookie: it is not readable from JavaScript, is sent automatically with
 *   `credentials: 'include'`, and is rotated by the API on every refresh.
 *   `lib/api.ts` performs the silent refresh when a request returns 401.
 * - The refresh cookie is expected to be `Secure; HttpOnly; SameSite=Lax`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { apiFetch, getAccessToken, logoutRequest, setAccessToken } from '@/lib/api';
import type { LoginRequest, TokenResponse, User } from '@/types/api';

export interface AuthContextValue {
  user: User | null;
  /** True while the session is being restored on first load. */
  isLoading: boolean;
  isAuthenticated: boolean;
  /** Set when the last sign-in attempt failed. */
  error: string | null;
  signIn: (credentials: LoginRequest) => Promise<void>;
  signOut: () => Promise<void>;
  /** Re-read the signed-in user (e.g. after a profile update). */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const profile = await apiFetch<User>('/auth/me');
      setUser(profile);
    } catch {
      setUser(null);
    }
  }, []);

  // Restore the session on first load: the httpOnly refresh cookie is exchanged
  // for a short-lived access token by the API's refresh endpoint.
  useEffect(() => {
    let cancelled = false;
    const restore = async (): Promise<void> => {
      setIsLoading(true);
      try {
        // A refresh attempt with no cookie returns 401; that is a normal
        // "signed out" state rather than an error.
        const refreshed = await apiFetch<TokenResponse>('/auth/refresh', {
          method: 'POST',
          allowRefresh: false,
        });
        if (cancelled) return;
        if (refreshed?.access_token) {
          setAccessToken(refreshed.access_token);
          await refreshUser();
        }
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    void restore();
    return () => {
      cancelled = true;
    };
  }, [refreshUser]);

  const signIn = useCallback(
    async (credentials: LoginRequest): Promise<void> => {
      setError(null);
      try {
        const tokens = await apiFetch<TokenResponse>('/auth/login', {
          method: 'POST',
          body: credentials,
          allowRefresh: false,
        });
        setAccessToken(tokens.access_token);
        await refreshUser();
      } catch (cause) {
        const message =
          cause instanceof Error ? cause.message : 'Sign-in failed. Please try again.';
        setError(message);
        throw cause;
      }
    },
    [refreshUser],
  );

  const signOut = useCallback(async (): Promise<void> => {
    await logoutRequest();
    setAccessToken(null);
    setUser(null);
    setError(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isAuthenticated: Boolean(user) || Boolean(getAccessToken()),
      error,
      signIn,
      signOut,
      refreshUser,
    }),
    [user, isLoading, error, signIn, signOut, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside an <AuthProvider>.');
  }
  return context;
}
