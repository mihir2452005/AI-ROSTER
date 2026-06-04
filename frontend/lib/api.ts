/* RoastGPT — API client for the FastAPI backend. */

import type {
  EndSessionResponse,
  RoastRequest,
  RoastResponse,
  SessionStateResponse,
  StartSessionRequest,
  StartSessionResponse,
} from "./types";
import { getAccessToken } from "./auth-api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

/** Default per-request timeout. Long enough for a slow backend, short enough
 * that a hung connection doesn't leave the user staring at "Loading…". */
const DEFAULT_TIMEOUT_MS = 15_000;

/** Thrown for non-2xx responses. `status` is the HTTP code, `detail` is the
 * server's human-readable message, and `code` is a friendly tag the UI can
 * branch on without parsing strings. */
export class ApiError extends Error {
  status: number;
  detail: string;
  code: ApiErrorCode;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.code = codeFor(status, detail);
  }
}

export type ApiErrorCode =
  | "not_found"
  | "session_ended"
  | "rate_limited"
  | "validation"
  | "free_tier"
  | "server"
  | "network"
  | "timeout"
  | "unknown";

function codeFor(status: number, detail: string): ApiErrorCode {
  if (status === 404) return "not_found";
  if (status === 410) return "session_ended";
  if (status === 429) return "rate_limited";
  if (status === 422) return "validation";
  if (status === 402) return "free_tier";
  if (status >= 500) return "server";
  if (detail === "timeout") return "timeout";
  if (detail.startsWith("NetworkError") || detail.includes("fetch")) return "network";
  return "unknown";
}

/** Maps an API error to a user-friendly message. */
export function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "not_found":      return "Session not found. It may have expired — start a new one.";
      case "session_ended":  return "This session has ended. Start a new one to keep roasting.";
      case "rate_limited":   return "You hit the message cap for this session. Start a new one to keep going.";
      case "free_tier":      return "You’ve used your 5 free messages. Subscribe to keep roasting.";
      case "validation":     return "Please check your input (1–2000 non-blank characters).";
      case "server":         return "Server hiccup. Try again in a moment.";
      case "network":        return "Can't reach the server. Check your connection.";
      case "timeout":        return "The server is taking too long. Try again in a moment.";
      default:               return err.detail || "Something went wrong.";
    }
  }
  return (err as Error)?.message || "Unknown error.";
}

interface RequestOptions extends RequestInit {
  /** Per-request timeout in ms. Defaults to DEFAULT_TIMEOUT_MS. Pass 0 to
   * disable (use sparingly — hung requests leave the user stuck). */
  timeoutMs?: number;
}

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init ?? {};
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }
  // Auto-inject bearer token if a logged-in user is present. This lets the
  // backend persist chat history + enforce the free-tier limit transparently.
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(rest.headers as Record<string, string> | undefined || {}),
  };
  if (!headers["Authorization"]) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers,
      cache: "no-store",
      ...rest,
      signal: controller.signal,
    });
  } catch (e: any) {
    if (e?.name === "AbortError") {
      throw new ApiError(0, "timeout");
    }
    throw new ApiError(0, `NetworkError: ${e?.message || "fetch failed"}`);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
  if (!res.ok) {
    let body = "";
    try { body = await res.text(); } catch { /* noop */ }
    // FastAPI 422 returns JSON like {"detail":[{...}]} — extract a short
    // message so we don't show the user the full validation dump.
    let detail = body || res.statusText;
    try {
      const j = JSON.parse(body);
      if (typeof j?.detail === "string") detail = j.detail;
      else if (Array.isArray(j?.detail) && j.detail[0]?.msg) detail = j.detail[0].msg;
    } catch { /* not JSON; keep raw */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () =>
    request<{
      status: string;
      library_loaded: boolean;
      roasts: number;
      personalities: number;
      intents: number;
    }>("/api/health"),

  startSession: (body: StartSessionRequest) =>
    request<StartSessionResponse>("/api/session/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  roast: (sessionId: string, body: RoastRequest) =>
    request<RoastResponse>(`/api/session/${sessionId}/roast`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  endSession: (sessionId: string) =>
    request<EndSessionResponse>(`/api/session/${sessionId}/end`, {
      method: "POST",
    }),

  getSession: (sessionId: string) =>
    request<SessionStateResponse>(`/api/session/${sessionId}`),
};
