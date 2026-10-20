/**
 * Typed fetch wrapper for the ScholarMind REST API.
 *
 * Responsibilities:
 *  - resolve the base URL from `import.meta.env` (never from a hard-coded host);
 *  - serialise query parameters and JSON bodies;
 *  - attach the in-memory access token;
 *  - normalise every failure into an `ApiError` with a machine-readable code;
 *  - silently refresh an expired access token using the API's httpOnly refresh
 *    cookie and replay the original request once.
 *
 * The access token is deliberately kept in a module-scoped variable rather than
 * `localStorage`: a persisted token is trivially exfiltrated by an XSS payload.
 * See `lib/auth.tsx`.
 */

import type {
  TokenResponse,
} from '@/types/api';

const RAW_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  'http://localhost:8000/api/v1';

/** Base URL without a trailing slash. */
export const API_BASE_URL = RAW_BASE_URL.replace(/\/+$/, '');

const REFRESH_PATH = '/auth/refresh';
const LOGOUT_PATH = '/auth/logout';

export type QueryValue = string | number | boolean | null | undefined | string[];

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** Set to false for requests that must not trigger a token refresh. */
  allowRefresh?: boolean;
}

export interface ApiErrorInit {
  status: number;
  code?: string;
  requestId?: string | null;
  details?: unknown;
}

/** Every failed API call surfaces as an `ApiError`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(message: string, init: ApiErrorInit) {
    super(message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code ?? 'unknown_error';
    this.requestId = init.requestId ?? null;
    this.details = init.details ?? null;
  }

  /** True when the request failed because the caller is not authenticated. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** True when the request never reached the server. */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

/* ------------------------------------------------------------------ *
 * In-memory token store
 * ------------------------------------------------------------------ */

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/* ------------------------------------------------------------------ *
 * Helpers
 * ------------------------------------------------------------------ */

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const normalisedPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${API_BASE_URL}${normalisedPath}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === null || value === undefined || value === '') continue;
      if (Array.isArray(value)) {
        for (const entry of value) {
          if (entry === null || entry === undefined || entry === '') continue;
          url.searchParams.append(key, String(entry));
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

function readRequestId(response: Response): string | null {
  return response.headers.get('x-request-id') ?? response.headers.get('x-requestid') ?? null;
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = readRequestId(response);
  let code = `http_${response.status}`;
  let message = `Request failed with status ${response.status}.`;
  let details: unknown = null;

  try {
    const text = await response.text();
    if (text) {
      const parsed: unknown = JSON.parse(text);
      if (parsed && typeof parsed === 'object') {
        const record = parsed as Record<string, unknown>;
        const candidateCode = record.code ?? record.error ?? record.type;
        if (typeof candidateCode === 'string') code = candidateCode;
        const candidateMessage =
          (typeof record.message === 'string' && record.message) ||
          (typeof record.detail === 'string' && record.detail) ||
          (Array.isArray(record.detail) && typeof record.detail[0] === 'string' ? record.detail[0] : '');
        if (candidateMessage) message = candidateMessage;
        details = record.detail ?? parsed;
      }
    }
  } catch {
    // Non-JSON error body (e.g. an HTML error page) — keep the generic message.
  }

  return new ApiError(message, { status: response.status, code, requestId, details });
}

/**
 * Attempt a silent token refresh using the API's httpOnly refresh cookie.
 * Returns `true` when a new access token was obtained.
 */
async function tryRefreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch(buildUrl(REFRESH_PATH), {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return false;
    const payload = (await response.json()) as TokenResponse;
    if (!payload?.access_token) return false;
    setAccessToken(payload.access_token);
    return true;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ *
 * Public API
 * ------------------------------------------------------------------ */

/**
 * Perform a JSON request against the API and return the decoded body.
 * Throws `ApiError` for every failure mode.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal, headers = {}, allowRefresh = true } = options;

  const requestHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...headers,
  };

  let payload: string | undefined;
  if (body !== undefined) {
    payload = JSON.stringify(body);
    requestHeaders['Content-Type'] = 'application/json';
  }

  const token = getAccessToken();
  if (token) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers: requestHeaders,
      body: payload,
      signal,
      // Required so the httpOnly refresh cookie travels with every request.
      credentials: 'include',
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(
      'Could not reach the ScholarMind API. Check your connection and try again.',
      { status: 0, code: 'network_error', details: cause },
    );
  }

  if (response.status === 401 && allowRefresh) {
    const refreshed = await tryRefreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, allowRefresh: false });
    }
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

/** Convenience wrapper for `GET`. */
export function apiGet<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'GET' });
}

/** Convenience wrapper for `POST`. */
export function apiPost<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'POST', body });
}

/** Convenience wrapper for `PATCH`. */
export function apiPatch<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'PATCH', body });
}

/** Convenience wrapper for `PUT`. */
export function apiPut<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'PUT', body });
}

/** Convenience wrapper for `DELETE`. */
export function apiDelete<T>(path: string, options: Omit<RequestOptions, 'method'> = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'DELETE' });
}

/**
 * Ask the API to invalidate the httpOnly refresh cookie. Safe to call when
 * unauthenticated.
 */
export async function logoutRequest(): Promise<void> {
  try {
    await fetch(buildUrl(LOGOUT_PATH), {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
  } catch {
    // Signing out locally must succeed even when the network is down.
  }
  setAccessToken(null);
}
