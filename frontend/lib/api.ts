/* RoastGPT â€” API client for the FastAPI backend. */

import type {
  EndSessionResponse,
  RoastRequest,
  RoastResponse,
  SessionStateResponse,
  StartSessionRequest,
  StartSessionResponse,
} from "./types";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "./auth-api";
import { ApiError, codeFor, friendlyError } from "./errors";

export { ApiError, codeFor, friendlyError };
export type { ApiErrorCode } from "./errors";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
// API versioning: every caller passes paths like "/api/v1/..." which
// get concatenated with API_BASE. The backend's `api_v1_alias` ASGI
// middleware strips the /v1 segment and forwards to the unversioned
// handler, so legacy clients on /api/* keep working while the frontend
// pins to v1. If/when v2 lands, switch all "/api/v1/" prefixes to
// "/api/v2/" and the backend's v2 middleware takes over.
if (!API_BASE && typeof window !== "undefined" && process.env.NODE_ENV === "production") {
  // Loud, once-per-load warning if the env var is missing in production.
  // Without this, every API call silently hits the Next.js origin and
  // 404s on every route â€” confusing to debug.
  // eslint-disable-next-line no-console
  console.warn(
    "[RoastGPT] NEXT_PUBLIC_API_URL is not set â€” API calls will fail in production."
  );
}

interface RequestOptions extends RequestInit {
  /** Per-request timeout in ms. Defaults to DEFAULT_TIMEOUT_MS. Pass 0 to
   * disable (use sparingly â€” hung requests leave the user stuck). */
  timeoutMs?: number;
  /** Internal: marks a request as a retry-after-refresh so we don't
   * loop forever on a perpetually-401 endpoint. Never set this in
   * application code. */
  __retried?: boolean;
  /** Optional AbortSignal â€” wired to the internal timeout controller. */
  signal?: AbortSignal;
}

const DEFAULT_TIMEOUT_MS = 15_000;

export async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init ?? {};
  // We intentionally pull __retried out so it doesn't end up in the
  // fetch init (which doesn't know about it) and so the local boolean
  // is the single source of truth on whether this is a retry.
  const { __retried, ...initRest } = (rest as RequestInit & { __retried?: boolean }) ?? {};
  const retried = __retried === true;

  // Combine caller's signal with our internal timeout signal.
  const controller = new AbortController();
  const onCallerAbort = () => controller.abort();
  if (init?.signal) {
    if (init.signal.aborted) controller.abort();
    else init.signal.addEventListener("abort", onCallerAbort, { once: true });
  }
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }

  // Auto-inject bearer token if a logged-in user is present. This lets
  // the backend persist chat history + enforce the free-tier limit
  // transparently.
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((initRest.headers as Record<string, string> | undefined) || {}),
  };
  if (!headers["Authorization"]) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      // Order matters: caller-supplied fetch options can override
      // signal/cache but not Authorization (auth wins for safety).
      cache: "no-store",
      ...initRest,
      headers,
      signal: controller.signal,
    });
  } catch (e) {
    const isAbort = e instanceof Error && e.name === "AbortError";
    throw new ApiError(0, isAbort ? "timeout" : `NetworkError: ${(e as Error)?.message || "fetch failed"}`);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    if (init?.signal) init.signal.removeEventListener("abort", onCallerAbort);
  }

  if (!res.ok) {
    let body = "";
    try { body = await res.text(); } catch { /* noop */ }
    // FastAPI 422 returns JSON like {"detail":[{...}]} — extract a
    // short message so we don't show the user the full validation
    // dump.
    let detail = body || res.statusText;
    let parsed: Record<string, unknown> | null = null;
    try {
      const j = JSON.parse(body);
      parsed = j && typeof j === "object" ? (j as Record<string, unknown>) : null;
      if (typeof j?.detail === "string") detail = j.detail;
      else if (Array.isArray(j?.detail) && j.detail[0]?.msg) detail = j.detail[0].msg;
    } catch { /* not JSON; keep raw */ }

    // 401 with a refresh token: try to refresh once and replay. Don't
    // recurse infinitely â€” only one retry, only if we actually HAD a
    // refresh token to begin with. This handles the "access token
    // expired mid-session" case without bouncing the user to /login.
    if (res.status === 401 && !retried && getRefreshToken()) {
      const ok = await tryRefresh();
      if (ok) {
        // Drop the stale Authorization from the original request so
        // we pick up the freshly-stored token.
        const { Authorization: _drop, ...restHeaders } = headers;
        return request<T>(path, {
          ...initRest,
          headers: restHeaders,
          signal: init?.signal,
          timeoutMs,
          __retried: true,
        } as RequestOptions);
      }
    }
    throw new ApiError(res.status, detail, parsed);
  }

  // Guard against non-JSON 2xx responses (e.g., an HTML proxy error
  // page leaking through). Without this, a SyntaxError from JSON.parse
  // would surface as a raw exception, bypassing every `instanceof
  // ApiError` branch in the UI.
  const text = await res.text();
  try {
    return text ? (JSON.parse(text) as T) : (undefined as T);
  } catch {
    throw new ApiError(res.status, "Invalid server response");
  }
}

// ---- Refresh coordination ------------------------------------------------

// Exported so auth-api.ts can re-use the same in-flight promise. A
// burst of 401s split between api.* and authApi.* (e.g., Promise.all
// in /account) would otherwise fire N concurrent refreshes.
let _refreshInFlight: Promise<boolean> | null = null;

export async function tryRefresh(): Promise<boolean> {
  if (_refreshInFlight) return _refreshInFlight;
  const refresh = getRefreshToken();
  if (!refresh) {
    clearTokens();
    return false;
  }
  _refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        // 4xx/5xx on refresh = refresh token is dead. Wipe all
        // tokens so the next request doesn't re-enter the retry
        // path.
        clearTokens();
        return false;
      }
      // The refresh endpoint returns JSON; a non-JSON response (e.g.,
      // a proxy 502 HTML page) means the network is broken, not that
      // the token is bad. Don't nuke the tokens in that case.
      const text = await res.text();
      const j = text ? JSON.parse(text) : null;
      if (!j?.access_token || !j?.refresh_token) {
        clearTokens();
        return false;
      }
      setTokens(j.access_token, j.refresh_token);
      return true;
    } catch {
      // Network failure during refresh: leave tokens in place so the
      // next request can try again. Clearing them here would log the
      // user out on a transient blip.
      return false;
    } finally {
      _refreshInFlight = null;
    }
  })();
  return _refreshInFlight;
}

export const api = {
  health: () =>
    request<{
      status: string;
      library_loaded: boolean;
      roasts: number;
      personalities: number;
      intents: number;
    }>("/api/v1/health"),

  startSession: (body: StartSessionRequest) =>
    request<StartSessionResponse>("/api/v1/session/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  roast: (sessionId: string, body: RoastRequest, opts?: { signal?: AbortSignal }) =>
    request<RoastResponse>(`/api/v1/session/${sessionId}/roast`, {
      method: "POST",
      body: JSON.stringify(body),
      signal: opts?.signal,
    }),

  endSession: (sessionId: string) =>
    request<EndSessionResponse>(`/api/v1/session/${sessionId}/end`, {
      method: "POST",
    }),

  getSession: (sessionId: string) =>
    request<SessionStateResponse>(`/api/v1/session/${sessionId}`),

  /**
   * Reconstruct a session from the `roast_sessions` table after a
   * server cold start wiped the in-memory store. Authenticated users
   * only — anonymous sessions aren't persisted. Requires the JWT
   * bearer token to be present (auto-injected by `request`).
   */
  recoverSession: (sessionId: string) =>
    request<SessionStateResponse>(`/api/v1/session/${sessionId}/recover`, {
      method: "POST",
    }),

  /** Mint (or re-use) a public share token for a session. */
  shareSession: (sessionId: string) =>
    request<{ share_url: string; token: string }>(`/api/v1/session/${sessionId}/share`, {
      method: "POST",
    }),

  /** Revoke an existing share token. */
  revokeShareSession: (sessionId: string) =>
    request<{ message: string }>(`/api/v1/session/${sessionId}/share`, {
      method: "DELETE",
    }),
};
