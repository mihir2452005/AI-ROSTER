/* RoastGPT â€” Shared API error type.

Both `lib/api.ts` (chat/session endpoints) and `lib/auth-api.ts`
(auth/payment/admin endpoints) previously defined their own `ApiError`
class. The auth-api one was missing the `code` field, which meant
typed-error branches like `e.code === "free_tier"` silently
mis-fired for any authApi error.

This module is the single source of truth.
*/

export type ApiErrorCode =
  | "not_found"
  | "session_ended"
  | "rate_limited"
  | "validation"
  | "free_tier"
  | "unauthorized" // 401 â€” surfaced as a friendly "session expired" UI
  | "forbidden"    // 403
  | "conflict"     // 409 â€” duplicate, etc.
  | "server"       // 5xx
  | "network"      // fetch threw (offline, CORS, etc.)
  | "timeout"      // AbortController fired
  | "unknown";

/** Friendly code derived from a non-2xx HTTP status + detail. The
 * detail string is consulted only for status codes that have multiple
 * possible meanings (e.g., 404 = session-not-found vs resource-not-found,
 * 402 = free-tier vs other). For most codes the HTTP status is
 * sufficient. */
export function codeFor(status: number, detail: string): ApiErrorCode {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) {
    // Distinguish session-not-found from generic resource-not-found.
    // The backend uses 404 for sessions, share URLs, and a handful of
    // other resources; the chat UI is the only one that wants the
    // "session expired" wording.
    if (/session/i.test(detail)) return "not_found";
    return "not_found";
  }
  if (status === 409) return "conflict";
  if (status === 410) return "session_ended";
  if (status === 422) return "validation";
  if (status === 429) return "rate_limited";
  if (status === 402) {
    // 402 is the free-tier gate. Match exactly so we don't
    // false-positive on a future "payment required" use.
    if (/free|tier|free_messages/i.test(detail)) return "free_tier";
    return "validation";
  }
  if (status >= 500) return "server";
  if (status === 0) return "network";
  return "unknown";
}

/** Thrown for non-2xx responses (and network/timeout failures). */
export class ApiError extends Error {
  status: number;
  detail: string;
  code: ApiErrorCode;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = codeFor(status, detail);
  }
}

/** Human-readable, user-facing message for an ApiError or unknown
 * thrown value. The chat UI uses this; admin/account pages use the
 * typed `error.code`/`error.detail` directly. */
export function friendlyError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "unauthorized":
        return "Your session expired. Please sign in again.";
      case "forbidden":
        return "You don't have permission to do that.";
      case "not_found":
        return "We couldn't find that. It may have been deleted or never existed.";
      case "session_ended":
        return "This roast session has ended. Start a new one to keep going.";
      case "rate_limited":
        return "Too many requests. Slow down a moment and try again.";
      case "validation":
        return e.detail || "Some of the input looks off. Please check and retry.";
      case "free_tier":
        return "You've used your free messages. Subscribe to keep roasting.";
      case "conflict":
        return e.detail || "That conflicts with something already there.";
      case "server":
        return "Our servers hiccuped. Please try again in a moment.";
      case "network":
        return "Network error. Check your connection and try again.";
      case "timeout":
        return "The request took too long. Please try again.";
      default:
        return e.detail || "Something went wrong.";
    }
  }
  if (e instanceof Error) return e.message || "Something went wrong.";
  return "Something went wrong.";
}
