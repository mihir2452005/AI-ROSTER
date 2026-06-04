/* RoastGPT — Auth/Payment API client for the FastAPI backend. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

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

export function setTokens(access: string, refresh: string) {
  const s = _store();
  if (!s) return;
  s.setItem(TOKEN_KEY, access);
  s.setItem(REFRESH_KEY, refresh);
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
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function cacheUser(user: User) {
  const s = _store();
  if (!s) return;
  s.setItem(USER_KEY, JSON.stringify(user));
  s.setItem(TOKEN_VERSION_KEY, String(user.token_version ?? 0));
}

export function getStoredTokenVersion(): number {
  const s = _store();
  if (!s) return 0;
  return Number(s.getItem(TOKEN_VERSION_KEY) || "0");
}

/**
 * Broadcast a cross-component "the auth state just changed" signal.
 * Used by the pricing page after a successful payment so the HeaderAuth
 * component (which is in the root layout and doesn't unmount on
 * navigation) can drop the "⭐ Subscribe" badge without a full reload.
 */
export function emitAuthRefresh(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("roastgpt:auth-refresh"));
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init ?? {};
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }

  // Auto-inject Authorization header if we have a token
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(rest.headers as Record<string, string> || {}),
  };
  const access = getAccessToken();
  if (access && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${access}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (e: any) {
    if (e?.name === "AbortError") throw new ApiError(0, "timeout");
    throw new ApiError(0, `NetworkError: ${e?.message || "fetch failed"}`);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
  if (!res.ok) {
    let body = "";
    try { body = await res.text(); } catch { /* noop */ }
    let detail = body || res.statusText;
    try {
      const j = JSON.parse(body);
      if (typeof j?.detail === "string") detail = j.detail;
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// ---- Types ----
export interface User {
  id: number;
  email: string;
  full_name: string | null;
  gender_preference: "male" | "female" | "neutral";
  is_verified: boolean;
  is_admin: boolean;
  free_messages_used: number;
  has_active_subscription: boolean;
  created_at: string;
  token_version: number;
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
      "/api/auth/register", { method: "POST", body: JSON.stringify(data) }
    );
    setTokens(r.access_token, r.refresh_token);
    // Eagerly fetch and cache the user so the header reflects the new
    // account immediately, and so token_version invalidation works
    // across tabs in the future.
    try {
      const u = await authApi.me();
      cacheUser(u);
      emitAuthRefresh();
    } catch { /* best-effort */ }
    return r;
  },

  login: async (data: { email: string; password: string }) => {
    const r = await request<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>(
      "/api/auth/login", { method: "POST", body: JSON.stringify(data) }
    );
    setTokens(r.access_token, r.refresh_token);
    try {
      const u = await authApi.me();
      cacheUser(u);
      emitAuthRefresh();
    } catch { /* best-effort */ }
    return r;
  },

  refresh: async (refreshToken: string) => {
    const r = await request<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>(
      "/api/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }
    );
    setTokens(r.access_token, r.refresh_token);
    return r;
  },

  me: async () => {
    const u = await request<User>("/api/auth/me");
    cacheUser(u);
    return u;
  },

  updateMe: async (data: { full_name?: string; gender_preference?: string }) => {
    const u = await request<User>("/api/auth/me", { method: "PATCH", body: JSON.stringify(data) });
    cacheUser(u);
    return u;
  },

  changePassword: (data: { current_password: string; new_password: string }) =>
    request<{ message: string }>("/api/auth/change-password", { method: "POST", body: JSON.stringify(data) }),

  // Server-side logout: bumps token_version so the current token is
  // immediately invalid, and clears local state. Falls back to local
  // clear if the network call fails (we don't want a transient network
  // error to leave the user "logged in" with a dead token).
  logout: async () => {
    try {
      await request<{ message: string }>("/api/auth/logout", { method: "POST" });
    } catch {
      // best-effort: still clear local state
    }
    clearTokens();
    emitAuthRefresh();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  },
};

// ---- Payment API ----
export const paymentsApi = {
  listPlans: () => request<{ plans: Plan[] }>("/api/payments/plans"),

  createOrder: (planCode: string) =>
    request<OrderResponse>("/api/payments/create-order", {
      method: "POST",
      body: JSON.stringify({ plan_code: planCode }),
    }),

  verifyPayment: (data: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) =>
    request<{ message: string; subscription_id: number; current_period_end: string }>(
      "/api/payments/verify", { method: "POST", body: JSON.stringify(data) }
    ),

  history: () => request<Payment[]>("/api/payments/history"),
};

export const subscriptionsApi = {
  my: () => request<{ subscriptions: Subscription[] }>("/api/subscriptions/me"),
  cancel: () => request<{ message: string; current_period_end: string }>(
    "/api/subscriptions/cancel", { method: "POST" }
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
  list: (params?: { skip?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{ items: ChatHistoryItem[]; total: number }>(
      `/api/history${q ? `?${q}` : ""}`
    );
  },
  clear: () => request<{ message: string; deleted: number }>("/api/history", { method: "DELETE" }),
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
  free_messages_used: number;
  created_at: string;
  has_active_subscription: boolean;
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
  stats: () => request<AdminStats>("/api/admin/stats"),

  listUsers: (params?: { skip?: number; limit?: number; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.search) qs.set("search", params.search);
    const q = qs.toString();
    return request<{ users: AdminUser[]; total: number }>(`/api/admin/users${q ? `?${q}` : ""}`);
  },

  getUser: (id: number) => request<AdminUser>(`/api/admin/users/${id}`),

  updateUser: (id: number, patch: { is_active?: boolean; is_verified?: boolean; is_admin?: boolean }) =>
    request<{ message: string }>(`/api/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  grantSubscription: (data: { user_id: number; plan_code: string; duration_days?: number }) =>
    request<{ message: string; subscription_id: number; current_period_end: string }>(
      "/api/admin/grant-subscription", { method: "POST", body: JSON.stringify(data) }
    ),

  leaderboard: (period: "week" | "month" = "week", limit = 10) =>
    request<{ period: string; entries: LeaderboardEntry[] }>(
      `/api/admin/leaderboard?period=${period}&limit=${limit}`
    ),
};
