/* RoastGPT â€” Auth/Payment API client for the FastAPI backend.

Uses the shared `request` / `ApiError` / `tryRefresh` from `lib/api.ts`
so a 401 burst from any combination of api.* and authApi.* calls
triggers exactly ONE refresh, and so all thrown errors carry a typed
`.code` that the UI can branch on.
*/

import { ApiError, codeFor, friendlyError, request, tryRefresh } from "./api";

export { ApiError, codeFor, friendlyError };
export type { ApiErrorCode } from "./api";

// ---- Auth token storage ----
// Uses sessionStorage (NOT localStorage) so tokens don't survive a tab
// close. This is a deliberate trade-off: refresh persists within a tab
// (good UX), but closing the tab invalidates the session (much better
// security than localStorage, which is exposed to every XSS payload
// for the lifetime of the subdomain).
const TOKEN_KEY = "roastgpt_access_token";
const REFRESH_KEY = "roastgpt_refresh_token";
const USER_KEY = "roastgpt_user_cache";
// Echoed by the server's /api/auth/me. If the local stored version
// doesn't match, the token has been invalidated server-side (logout,
// password change, admin deactivation) and we force a re-login.
const TOKEN_VERSION_KEY = "roastgpt_token_version";

function _store(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

export function getAccessToken(): string | null {
  return _store()?.getItem(TOKEN_KEY) ?? null;
}

export function getRefreshToken(): string | null {
  return _store()?.getItem(REFRESH_KEY) ?? null;
}

export function authHeader(): Record<string, string> {
  const t = getAccessToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function setTokens(access: string, refresh: string) {
  const s = _store();
  if (!s) return;
  // Wrap in try/catch so a full sessionStorage (rare but possible on
  // shared kiosk browsers) doesn't break login. A friendly error
  // surfaces via the next request rather than a thrown exception
  // from the storage layer.
  try {
    s.setItem(TOKEN_KEY, access);
    s.setItem(REFRESH_KEY, refresh);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[RoastGPT] Failed to store auth tokens:", e);
  }
}

export function clearTokens() {
  const s = _store();
  if (!s) return;
  s.removeItem(TOKEN_KEY);
  s.removeItem(REFRESH_KEY);
  s.removeItem(USER_KEY);
  s.removeItem(TOKEN_VERSION_KEY);
}

export function getCachedUser(): User | null {
  const s = _store();
  if (!s) return null;
  const raw = s.getItem(USER_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    // Defensive: only return a shape that looks like a User. A
    // hand-edited sessionStorage entry with bogus data shouldn't
    // crash the header.
    if (parsed && typeof parsed === "object" && "id" in parsed && "email" in parsed) {
      return parsed as User;
    }
  } catch {
    /* fall through */
  }
  return null;
}

export function cacheUser(user: User) {
  const s = _store();
  if (!s) return;
  try {
    s.setItem(USER_KEY, JSON.stringify(user));
    s.setItem(TOKEN_VERSION_KEY, String(user.token_version ?? 0));
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[RoastGPT] Failed to cache user:", e);
  }
}

export function getStoredTokenVersion(): number {
  const s = _store();
  if (!s) return 0;
  const n = Number(s.getItem(TOKEN_VERSION_KEY) || "0");
  return Number.isFinite(n) ? n : 0;
}

/**
 * Broadcast a cross-component "the auth state just changed" signal.
 * Used by the pricing page after a successful payment, by login /
 * register / logout / profile updates, so the HeaderAuth component
 * (which is in the root layout and doesn't unmount on navigation) can
 * drop the "â­ Subscribe" badge without a full reload.
 *
 * Same-tab only. Cross-tab sync would require a `storage` event
 * listener (and sessionStorage doesn't fire `storage` for the
 * originating tab). If we ever switch to localStorage, add the
 * listener too.
 */
export function emitAuthRefresh(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("roastgpt:auth-refresh"));
}

// ---- Types ----
export interface User {
  id: number;
  email: string;
  full_name: string | null;
  gender_preference: "male" | "female" | "neutral";
  is_verified: boolean;
  is_admin: boolean;
  role?: string;
  free_messages_used: number;
  has_active_subscription: boolean;
  created_at: string;
  token_version: number;
  avatar_url?: string | null;
  is_banned?: boolean;
  ban_reason?: string | null;
  banned_at?: string | null;
  last_login_at?: string | null;
  favorite_mode?: string | null;
  favorite_personality?: string | null;
}

export interface UserStats {
  total_messages: number;
  total_sessions: number;
  total_score: number;
  average_score: number;
  best_score: number;
  score_by_mode: Record<string, { count: number; total: number }>;
  score_by_personality: Record<string, { count: number; total: number }>;
  recent_topics: string[];
  rank: number | null;
  rank_period: "daily" | "weekly" | "monthly" | "all_time" | null;
  achievements_unlocked: number;
  achievements_total: number;
}

export interface Plan {
  id: number;
  plan_code: string;
  name: string;
  price_paise: number;
  price_display: string;
  currency: string;
  duration_days: number;
  features: Record<string, unknown>;
}

export interface Subscription {
  id: number;
  plan_code: string;
  plan_name: string;
  status: "active" | "cancelled" | "past_due" | "completed" | "pending";
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  admin_granted: boolean;
  created_at: string;
}

export interface Payment {
  id: number;
  amount: number;
  currency: string;
  status: string;
  description: string | null;
  created_at: string;
}

export interface OrderResponse {
  order_id: string;
  amount: number;
  currency: string;
  plan_code: string;
  plan_name: string;
  key_id: string;
}

// ---- Auth API ----
export const authApi = {
  register: async (data: { email: string; password: string; full_name?: string; gender_preference?: string }) => {
    const r = await request<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>(
      "/api/v1/auth/register", { method: "POST", body: JSON.stringify(data) }
    );
    setTokens(r.access_token, r.refresh_token);
    // Eagerly fetch and cache the user so the header reflects the new
    // account immediately. Even if this fails, the auth-refresh
    // signal still fires so HeaderAuth re-evaluates.
    try {
      const u = await authApi.me();
      cacheUser(u);
    } catch { /* best-effort */ }
    emitAuthRefresh();
    return r;
  },

  login: async (data: { email: string; password: string }) => {
    const r = await request<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>(
      "/api/v1/auth/login", { method: "POST", body: JSON.stringify(data) }
    );
    setTokens(r.access_token, r.refresh_token);
    try {
      const u = await authApi.me();
      cacheUser(u);
    } catch { /* best-effort */ }
    emitAuthRefresh();
    return r;
  },

  refresh: async (refreshToken: string) => {
    const r = await request<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>(
      "/api/v1/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }
    );
    setTokens(r.access_token, r.refresh_token);
    return r;
  },

  me: async () => {
    const u = await request<User>("/api/v1/auth/me");
    cacheUser(u);
    return u;
  },

  updateMe: async (data: { full_name?: string; gender_preference?: string }) => {
    const u = await request<User>("/api/v1/auth/me", { method: "PATCH", body: JSON.stringify(data) });
    cacheUser(u);
    // Profile changes affect what the header shows (initial letter,
    // name, gender-driven CTA copy). Notify it.
    emitAuthRefresh();
    return u;
  },

  changePassword: (data: { current_password: string; new_password: string }) =>
    request<{ message: string }>("/api/v1/auth/change-password", { method: "POST", body: JSON.stringify(data) }),

  // Account / verification / password / avatar / favorites / stats
  sendVerification: () =>
    request<{ message: string }>("/api/v1/auth/send-verification", { method: "POST" }),

  verifyEmail: (token: string) =>
    request<{ message: string }>("/api/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }),

  forgotPassword: (email: string) =>
    request<{ message: string }>("/api/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),

  resetPassword: (token: string, new_password: string) =>
    request<{ message: string }>("/api/v1/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) }),

  deleteMe: () =>
    request<{ message: string }>("/api/v1/auth/me", { method: "DELETE" }),

  uploadAvatar: (avatar_data_uri: string) =>
    request<{ avatar_url: string }>("/api/v1/auth/me/avatar", { method: "POST", body: JSON.stringify({ avatar_data_uri }) }),

  myStats: () => request<UserStats>("/api/v1/auth/me/stats"),

  setFavorites: (data: { favorite_mode?: string | null; favorite_personality?: string | null }) =>
    request<User>("/api/v1/auth/me/favorites", { method: "PUT", body: JSON.stringify(data) }),

  // Server-side logout: bumps token_version so the current token is
  // immediately invalid, and clears local state. Falls back to local
  // clear if the network call fails (we don't want a transient network
  // error to leave the user "logged in" with a dead token).
  logout: async () => {
    try {
      await request<{ message: string }>("/api/v1/auth/logout", { method: "POST" });
    } catch {
      // best-effort: still clear local state
    }
    clearTokens();
    emitAuthRefresh();
    if (typeof window !== "undefined") {
      // Full nav is fine here — the user is logging out and there's
      // no chat state to preserve. router.push would be cleaner but
      // this module is imported from non-React code paths in places.
      window.location.href = "/login";
    }
  },

  // Admin auth (separate JWT + is_admin gate)
  adminLogin: async (data: { email: string; password: string }) => {
    const r = await request<{ access_token: string; token_type: string; expires_in: number }>(
      "/api/v1/auth/admin/login", { method: "POST", body: JSON.stringify(data) }
    );
    // Admin login uses a different storage key so it doesn't clobber the
    // user session token.
    if (typeof window !== "undefined") {
      try { sessionStorage.setItem("roastgpt_admin_token", r.access_token); } catch { /* ignore */ }
    }
    return r;
  },

  adminMe: async () => {
    const t = typeof window !== "undefined" ? sessionStorage.getItem("roastgpt_admin_token") : null;
    if (!t) throw new Error("not logged in as admin");
    return request<User>("/api/v1/auth/me", { headers: { Authorization: `Bearer ${t}` } });
  },

  adminLogout: () => {
    if (typeof window !== "undefined") {
      try { sessionStorage.removeItem("roastgpt_admin_token"); } catch { /* ignore */ }
    }
  },
};

// ---- Payment API ----
export const paymentsApi = {
  listPlans: () => request<{ plans: Plan[] }>("/api/v1/payments/plans"),

  createOrder: (planCode: string) =>
    request<OrderResponse>("/api/v1/payments/create-order", {
      method: "POST",
      body: JSON.stringify({ plan_code: planCode }),
    }),

  verifyPayment: (data: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) =>
    request<{ message: string; subscription_id: number; current_period_end: string }>(
      "/api/v1/payments/verify", { method: "POST", body: JSON.stringify(data) }
    ),

  history: () => request<Payment[]>("/api/v1/payments/history"),
};

export const subscriptionsApi = {
  my: () => request<{ subscriptions: Subscription[] }>("/api/v1/subscriptions/me"),
  cancel: async () => {
    const r = await request<{ message: string; current_period_end: string }>(
      "/api/v1/subscriptions/cancel", { method: "POST" }
    );
    // Cancellation flips cancel_at_period_end, which the header
    // badge / account page both need to see.
    emitAuthRefresh();
    return r;
  },
  // Upgrade creates a Razorpay order (in live mode) or swaps the
  // plan directly (in dev mode). Returns a discriminated payload
  // the pricing page uses to decide whether to open the checkout.
  upgrade: (target_plan_code: string) =>
    request<{
      order_id?: string;
      amount?: number;
      currency?: string;
      key_id?: string;
      plan?: string;
      payment_required: boolean;
      message: string;
      current_period_end?: string;
    }>("/api/v1/subscriptions/upgrade", {
      method: "POST",
      body: JSON.stringify({ target_plan_code }),
    }),
  downgrade: (target_plan_code: string) =>
    request<{ message: string; current_period_end: string; scheduled_plan: string }>(
      "/api/v1/subscriptions/downgrade", {
        method: "POST",
        body: JSON.stringify({ target_plan_code }),
      }
    ),
};

// ---- History API ----
export interface ChatHistoryItem {
  id: number;
  message: string;
  is_user: boolean;
  roast_response: string | null;
  score_total: number;
  created_at: string;
}

export const historyApi = {
  list: (params?: { skip?: number; limit?: number; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.q) qs.set("q", params.q);
    const q = qs.toString();
    return request<{ items: ChatHistoryItem[]; total: number }>(
      `/api/v1/history${q ? `?${q}` : ""}`
    );
  },
  clear: () => request<{ message: string; deleted: number }>("/api/v1/history", { method: "DELETE" }),
  // Note: we use raw `fetch` here (not the shared `request()` helper)
  export: (format: "txt" | "md" | "json" = "txt") => {
    const base = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
      (typeof window !== "undefined" && (window as unknown as { __API_BASE__?: string }).__API_BASE__) ||
      "";
    return fetch(
      `${base}/api/v1/history/export?format=${format}`,
      { headers: authHeader() },
    );
  },
  /** Continue Previous Chat: list persisted sessions grouped by session_id. */
  sessions: (params?: { skip?: number; limit?: number; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.q) qs.set("q", params.q);
    const q = qs.toString();
    return request<{
      sessions: Array<{
        session_id: string;
        mode: string;
        personality: string;
        message_count: number;
        last_message_at: string;
        is_ended: boolean;
        score_total: number;
        preview: string | null;
      }>;
      total: number;
    }>(`/api/v1/history/sessions${q ? `?${q}` : ""}`);
  },
};

// ---- Admin API ----
// Only callable by users with is_admin=true (enforced server-side).
export interface AdminUser {
  id: number;
  // Server returns masked_email only (PII protection). UI shows it as-is.
  masked_email: string;
  full_name: string | null;
  gender_preference: string;
  is_active: boolean;
  is_verified: boolean;
  is_admin: boolean;
  role?: string;
  free_messages_used: number;
  created_at: string;
  has_active_subscription: boolean;
  is_banned?: boolean;
  ban_reason?: string | null;
  banned_at?: string | null;
}

export interface LeaderboardEntry {
  user_id: number;
  masked_email: string;
  full_name: string | null;
  total_damage: number;
  message_count: number;
  rank: number;
}

export interface AdminStats {
  total_users: number;
  active_users: number;
  active_subscriptions: number;
  total_payments: number;
  total_revenue_paise: number;
}

export const adminApi = {
  stats: () => request<AdminStats>("/api/v1/admin/stats"),

  listUsers: (params?: { skip?: number; limit?: number; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.search) qs.set("search", params.search);
    const q = qs.toString();
    return request<{ users: AdminUser[]; total: number }>(`/api/v1/admin/users${q ? `?${q}` : ""}`);
  },

  getUser: (id: number) => request<AdminUser>(`/api/v1/admin/users/${id}`),

  updateUser: (id: number, patch: { is_active?: boolean; is_verified?: boolean; is_admin?: boolean; role?: string }) =>
    request<{ message: string }>(`/api/v1/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  banUser: (id: number, reason: string) =>
    request<{ message: string }>(`/api/v1/admin/users/${id}/ban`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  unbanUser: (id: number) =>
    request<{ message: string }>(`/api/v1/admin/users/${id}/unban`, { method: "POST" }),

  listRoles: () =>
    request<{ roles: Array<{ name: string; rank: number; permissions: string[] }> }>(
      "/api/v1/admin/roles"
    ),

  listFeatureFlags: () => request<{ flags: Array<{ key: string; enabled: boolean; description: string | null; updated_at: string | null }> }>(
    "/api/v1/admin/feature-flags"
  ),

  upsertFeatureFlag: (key: string, enabled: boolean, description?: string) =>
    request<{ message: string }>("/api/v1/admin/feature-flags", {
      method: "PUT",
      body: JSON.stringify({ key, enabled, description }),
    }),

  listAuditLogs: (params?: { action?: string; skip?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.action) qs.set("action", params.action);
    if (params?.skip !== undefined) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{ logs: Array<{
      id: number;
      actor_user_id: number | null;
      actor_ip: string | null;
      action: string;
      target_user_id: number | null;
      details: Record<string, unknown> | null;
      created_at: string;
    }>; total: number }>(`/api/v1/admin/audit-logs${q ? `?${q}` : ""}`);
  },

  chartsSignups: (days = 30) =>
    request<{ days: number; series: Array<{ date: string; count: number }> }>(
      `/api/v1/admin/charts/signups?days=${days}`
    ),

  chartsChats: (days = 30) =>
    request<{ days: number; series: Array<{ date: string; count: number }> }>(
      `/api/v1/admin/charts/chats?days=${days}`
    ),

  userAchievements: (id: number) =>
    request<{
      achievements: Array<{
        key: string;
        name: string;
        description: string;
        emoji: string;
        category: string;
        rarity: string;
        points: number;
        unlocked: boolean;
        unlocked_at: string | null;
      }>;
    }>(`/api/v1/admin/users/${id}/achievements`),

  grantSubscription: (data: { user_id: number; plan_code: string; duration_days?: number }) =>
    request<{ message: string; subscription_id: number; current_period_end: string }>(
      "/api/v1/admin/grant-subscription", { method: "POST", body: JSON.stringify(data) }
    ),

  leaderboard: (period: "week" | "month" = "week", limit = 10) =>
    request<{ period: string; entries: LeaderboardEntry[] }>(
      `/api/admin/leaderboard?period=${period}&limit=${limit}`
    ),
};


// =============================================================================
// Round 9: contact, notifications, system status
// =============================================================================


export interface ContactMessage {
  id: number;
  name: string;
  email: string;
  subject: string;
  message: string;
  status: "new" | "in_progress" | "closed" | "spam";
  ip: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export interface ActivityItem {
  id: number;
  action: string;
  label: string;
  icon: string;
  created_at: string;
  details: Record<string, unknown> | null;
}

export interface SystemStatus {
  status: "healthy" | "degraded" | "unhealthy";
  database: string;
  redis: string;
  queue: string;
  sentry: string;
  version: string;
  uptime_seconds: number;
  maintenance_mode: boolean;
  build_sha: string | null;
}


export const contactApi = {
  submit: (data: { name: string; email: string; subject: string; message: string }) =>
    request<{ id: number; status: string; created_at: string }>(
      "/api/v1/contact",
      { method: "POST", body: JSON.stringify(data) }
    ),
};


export const notificationsApi = {
  list: (params?: { skip?: number; limit?: number; unread_only?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.unread_only) qs.set("unread_only", "true");
    const q = qs.toString();
    return request<{ items: Notification[]; total: number; unread_count: number }>(
      `/api/v1/notifications${q ? `?${q}` : ""}`
    );
  },
  markRead: (ids: number[]) =>
    request<{ updated: number }>("/api/v1/notifications/mark-read", {
      method: "POST", body: JSON.stringify({ ids }),
    }),
  markAllRead: () =>
    request<{ updated: number }>("/api/v1/notifications/mark-all-read", {
      method: "POST",
    }),
  activity: (params?: { skip?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{ items: ActivityItem[]; total: number }>(
      `/api/v1/auth/me/activity${q ? `?${q}` : ""}`
    );
  },
};


export const systemApi = {
  status: () => request<SystemStatus>("/api/v1/system/status"),
  // Returns raw text (Prometheus format). Use a plain fetch so the
  // shared `request` helper doesn't try to JSON-parse it.
  metrics: async (): Promise<string> => {
    const base = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
      (typeof window !== "undefined" && (window as unknown as { __API_BASE__?: string }).__API_BASE__) ||
      "";
    const r = await fetch(`${base}/api/v1/system/metrics`);
    if (!r.ok) throw new Error(`metrics fetch failed: ${r.status}`);
    return r.text();
  },
};


// Admin-side extensions for Round 9 endpoints. The broadcast helper
// accepts `target: "all"` or `target: "<user_id>"` (string) to match
// the server's contract.
export const adminContactApi = {
  list: (params?: { status?: string; skip?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{ messages: ContactMessage[]; total: number }>(
      `/api/v1/admin/contact-messages${q ? `?${q}` : ""}`
    );
  },
  updateStatus: (id: number, status: "new" | "in_progress" | "closed" | "spam") =>
    request<{ message: string; id: number; status: string }>(
      `/api/v1/admin/contact-messages/${id}?status=${status}`,
      { method: "PATCH" }
    ),
};

export const adminNotificationsApi = {
  broadcast: (data: {
    title: string;
    body: string;
    kind?: string;
    link?: string;
    target: "all" | string;
  }) =>
    request<{ delivered_to: number; kind: string; id?: number }>(
      "/api/v1/admin/notifications/broadcast",
      { method: "POST", body: JSON.stringify(data) }
    ),
};


// Re-export the shared refresh so non-React callers can trigger a
// refresh explicitly if they need to (e.g., background poll loops).
export { tryRefresh };
