import type { ApiErrorBody, ApiErrorResponse, Industry } from "@nql/shared-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const CSRF_COOKIE = "nql_csrf";
const CSRF_HEADER = "x-csrf-token";

/**
 * A failed API call, carrying the backend's stable error code and the request id so a
 * user-reported problem can be found in the server log.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.requestId = body.requestId;
    this.details = body.details;
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** True when retrying the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.status === 429 || this.status >= 500;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  industry?: Industry;
  /** Skip the automatic refresh-and-retry on 401. Used by the auth calls themselves. */
  skipRefresh?: boolean;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * A single in-flight refresh, shared by every 401 that happens concurrently. Without
 * this, five parallel queries failing at once would fire five refreshes and rotate the
 * token four times more than necessary — which the reuse detector would flag.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      return response.ok;
    } catch {
      return false;
    } finally {
      // Cleared on the next tick so callers awaiting this promise all see the result.
      queueMicrotask(() => {
        refreshInFlight = null;
      });
    }
  })();

  return refreshInFlight;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {
    code: "unknown_error",
    message: response.statusText || "The request failed.",
    requestId: response.headers.get("x-request-id") ?? "-",
    details: {},
  };
  try {
    const parsed = (await response.json()) as ApiErrorResponse;
    if (parsed?.error) body = parsed.error;
  } catch {
    // A non-JSON error body (a proxy timeout page, for example) keeps the default.
  }
  return new ApiError(response.status, body);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, industry, skipRefresh, headers, ...rest } = options;
  const method = (rest.method ?? "GET").toUpperCase();

  const requestHeaders = new Headers(headers);
  if (body !== undefined) {
    requestHeaders.set("content-type", "application/json");
  }
  if (industry) {
    requestHeaders.set("x-industry", industry);
  }
  // Cookie-authenticated mutations carry the double-submit CSRF token.
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) requestHeaders.set(CSRF_HEADER, csrf);
  }

  const send = (): Promise<Response> =>
    fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      method,
      headers: requestHeaders,
      // Cookies are the transport for the session; nothing is read from JS storage.
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  let response = await send();

  if (response.status === 401 && !skipRefresh) {
    if (await refreshSession()) {
      // The CSRF cookie is reissued by refresh, so re-read it before retrying.
      if (!SAFE_METHODS.has(method)) {
        const csrf = readCookie(CSRF_COOKIE);
        if (csrf) requestHeaders.set(CSRF_HEADER, csrf);
      }
      response = await send();
    }
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export { API_BASE_URL };
