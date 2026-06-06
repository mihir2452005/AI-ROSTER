"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  adminApi,
  adminContactApi,
  adminNotificationsApi,
  authApi,
  paymentsApi,
  getAccessToken,
  systemApi,
  type AdminUser,
  type AdminStats,
  type ContactMessage,
  type LeaderboardEntry,
  type Plan,
  type SystemStatus,
  type User,
} from "../../lib/auth-api";

type Tab = "stats" | "users" | "grant" | "leaderboard" | "audit" | "flags" | "charts" | "monitoring" | "contact" | "broadcast";

export default function AdminPage() {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);
  const [tab, setTab] = useState<Tab>("stats");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [search, setSearch] = useState("");
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [period, setPeriod] = useState<"week" | "month">("week");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [grantUserId, setGrantUserId] = useState("");
  const [grantPlan, setGrantPlan] = useState("pro");
  const [grantDuration, setGrantDuration] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [auditLogs, setAuditLogs] = useState<Array<{
    id: number;
    actor_user_id: number | null;
    actor_ip: string | null;
    action: string;
    target_user_id: number | null;
    details: Record<string, unknown> | null;
    created_at: string;
  }>>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditAction, setAuditAction] = useState("");
  const [flags, setFlags] = useState<Array<{ key: string; enabled: boolean; description: string | null; updated_at: string | null }>>([]);
  const [newFlagKey, setNewFlagKey] = useState("");
  const [newFlagDesc, setNewFlagDesc] = useState("");
  const [signupSeries, setSignupSeries] = useState<Array<{ date: string; count: number }>>([]);
  const [chatSeries, setChatSeries] = useState<Array<{ date: string; count: number }>>([]);
  // Pagination state for users + audit logs.
  const [userSkip, setUserSkip] = useState(0);
  const USER_PAGE = 25;
  const [auditSkip, setAuditSkip] = useState(0);
  const AUDIT_PAGE = 50;

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    authApi
      .me()
      .then((u) => {
        if (!u.is_admin) {
          setMessage("Admins only. Redirectingâ€¦");
          setTimeout(() => router.push("/"), 1500);
          return;
        }
        setMe(u);
        return Promise.all([adminApi.stats(), adminApi.listUsers({ limit: 50 })]);
      })
      .then((results) => {
        if (!results) return;
        const [s, u] = results;
        setStats(s);
        setUsers(u.users);
        setUserTotal(u.total);
        return paymentsApi.listPlans();
      })
      .then((p) => {
        if (p) setPlans(p.plans);
        return adminApi.leaderboard("week", 10);
      })
      .then((lb) => {
        if (lb) setLeaderboard(lb.entries);
      })
      .catch((e) => {
        if (e?.status === 401) router.push("/login");
        else setMessage("Error: " + (e?.detail || "load failed"));
      })
      .finally(() => setLoading(false));
  }, [router]);

  function reloadUsers(q?: string, skip = 0) {
    adminApi
      .listUsers({ search: q, limit: USER_PAGE, skip })
      .then((r) => {
        setUsers(r.users);
        setUserTotal(r.total);
        setUserSkip(skip);
      })
      .catch((e) => setMessage("Search failed: " + (e?.detail || "")));
  }

  function loadAudit() {
    adminApi
      .listAuditLogs({ action: auditAction || undefined, limit: AUDIT_PAGE, skip: auditSkip })
      .then((r) => {
        setAuditLogs(r.logs);
        setAuditTotal(r.total);
      })
      .catch((e) => setMessage("Audit log load failed: " + (e?.detail || "")));
  }

  function loadFlags() {
    adminApi
      .listFeatureFlags()
      .then((r) => setFlags(r.flags))
      .catch((e) => setMessage("Flag load failed: " + (e?.detail || "")));
  }

  function loadCharts() {
    Promise.all([adminApi.chartsSignups(30), adminApi.chartsChats(30)])
      .then(([s, c]) => {
        setSignupSeries(s.series);
        setChatSeries(c.series);
      })
      .catch((e) => setMessage("Charts failed: " + (e?.detail || "")));
  }

  // ---- Round 9: monitoring, contact inbox, broadcast ----
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [promText, setPromText] = useState<string>("");
  const [contactMessages, setContactMessages] = useState<ContactMessage[]>([]);

  function loadMonitoring() {
    systemApi
      .status()
      .then(setSystemStatus)
      .catch((e) => setMessage("Status failed: " + (e?.detail || "")));
    systemApi
      .metrics()
      .then(setPromText)
      .catch((e) => setMessage("Metrics failed: " + (e?.detail || "")));
  }

  function loadContact() {
    adminContactApi
      .list({ limit: 100 })
      .then((res) => setContactMessages(res.messages))
      .catch((e) => setMessage("Contact list failed: " + (e?.detail || "")));
  }

  function reloadTab(t: Tab) {
    setMessage("");
    if (t === "audit") loadAudit();
    else if (t === "flags") loadFlags();
    else if (t === "charts") loadCharts();
    else if (t === "monitoring") loadMonitoring();
    else if (t === "contact") loadContact();
  }

  function banUser(u: AdminUser) {
    const reason = prompt(`Ban ${u.masked_email}? Enter a reason (visible to the user):`);
    if (!reason) return;
    adminApi
      .banUser(u.id, reason)
      .then(() => {
        toast.success(`${u.masked_email} banned`);
        reloadUsers(search, userSkip);
      })
      .catch((e) => toast.error("Ban failed: " + (e?.message || "")));
  }

  function unbanUser(u: AdminUser) {
    if (!confirm(`Lift the ban on ${u.masked_email}?`)) return;
    adminApi
      .unbanUser(u.id)
      .then(() => {
        toast.success(`${u.masked_email} unbanned`);
        reloadUsers(search, userSkip);
      })
      .catch((e) => toast.error("Unban failed: " + (e?.message || "")));
  }

  function upsertFlag(key: string, enabled: boolean, description?: string) {
    adminApi
      .upsertFeatureFlag(key, enabled, description)
      .then(() => {
        toast.success(`Flag ${key} → ${enabled}`);
        loadFlags();
      })
      .catch((e) => toast.error("Flag update failed: " + (e?.message || "")));
  }

  function submitNewFlag(e: React.FormEvent) {
    e.preventDefault();
    if (!newFlagKey.trim()) return;
    upsertFlag(newFlagKey.trim(), true, newFlagDesc || undefined);
    setNewFlagKey("");
    setNewFlagDesc("");
  }

  // Cancel any in-flight debounce timer on unmount so we don't try to
  // setState on an unmounted component.
  useEffect(() => {
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, []);

function toggleUserFlag(u: AdminUser, key: "is_active" | "is_verified" | "is_admin", value: boolean) {
    setMessage("");
    adminApi
      .updateUser(u.id, { [key]: value })
      .then(() => {
        setMessage(`${u.masked_email} updated ✅`);
        reloadUsers(search);
      })
      .catch((e) => setMessage("Update failed: " + (e?.detail || "")));
  }

  function setUserRole(u: AdminUser, role: string) {
    if (!role) return;
    setMessage("");
    adminApi
      .updateUser(u.id, { role })
      .then(() => {
        setMessage(`${u.masked_email} role → ${role} ✅`);
        reloadUsers(search);
      })
      .catch((e) => setMessage("Update failed: " + (e?.detail || "")));
  }

  function submitGrant(e: React.FormEvent) {
    e.preventDefault();
    setMessage("");
    const uid = parseInt(grantUserId, 10);
    if (!uid) {
      setMessage("Enter a valid user ID.");
      return;
    }
    adminApi
      .grantSubscription({
        user_id: uid,
        plan_code: grantPlan,
        duration_days: grantDuration ? parseInt(grantDuration, 10) : undefined,
      })
      .then((r) => {
        setMessage(r.message + " until " + new Date(r.current_period_end).toLocaleDateString());
        setGrantUserId("");
        setGrantDuration("");
        reloadUsers(search);
      })
      .catch((e) => setMessage("Grant failed: " + (e?.detail || "")));
  }

  function switchLeaderboard(p: "week" | "month") {
    setPeriod(p);
    adminApi.leaderboard(p, 10).then((r) => setLeaderboard(r.entries));
  }

  if (loading) {
    return <main className="min-h-screen flex items-center justify-center text-slate-500">Loading adminâ€¦</main>;
  }
  if (!me?.is_admin) {
    return (
      <main className="min-h-screen flex items-center justify-center text-red-500">
        {message || "Admins only."}
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="max-w-5xl mx-auto">
        <header className="mb-6 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Admin dashboard</h1>
            <p className="text-sm text-slate-500">Signed in as {me.email}</p>
          </div>
          <a href="/" className="text-sm text-purple-600 hover:underline">â† Back to app</a>
        </header>

        {message && (
          <div className="mb-4 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-800 text-sm">
            {message}
          </div>
        )}

        <nav className="flex flex-wrap gap-2 mb-6 border-b border-slate-200">
          {([
            "stats", "users", "grant", "leaderboard",
            "audit", "flags", "charts",
            "monitoring", "contact", "broadcast",
          ] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); reloadTab(t); }}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t
                  ? "border-purple-600 text-purple-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t === "stats" ? "Stats" :
               t === "users" ? `Users (${userTotal})` :
               t === "grant" ? "Grant" :
               t === "leaderboard" ? "Leaderboard" :
               t === "audit" ? `Audit (${auditTotal})` :
               t === "flags" ? "Flags" :
               t === "monitoring" ? "Monitoring" :
               t === "contact" ? `Contact (${contactMessages.length})` :
               t === "broadcast" ? "Broadcast" :
               "Charts"}
            </button>
          ))}
        </nav>

        {tab === "stats" && stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Stat label="Total users" value={stats.total_users} />
            <Stat label="Active users" value={stats.active_users} />
            <Stat label="Active subs" value={stats.active_subscriptions} />
            <Stat label="Total payments" value={stats.total_payments} />
            <Stat label="Revenue" value={`â‚¹${(stats.total_revenue_paise / 100).toFixed(0)}`} />
          </div>
        )}

        {tab === "users" && (
          <div>
            <input
              type="text"
              placeholder="Search by email or nameâ€¦"
              value={search}
              onChange={(e) => {
                const v = e.target.value;
                setSearch(v);
                if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
                searchTimerRef.current = setTimeout(() => {
                  reloadUsers(v);
                }, 300);
              }}
              className="w-full mb-3 px-3 py-2 border border-slate-300 rounded-lg"
            />
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
                  <tr>
                    <th className="px-3 py-2">ID</th>
                    <th className="px-3 py-2">Email</th>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">Sub</th>
                    <th className="px-3 py-2">Active</th>
                    <th className="px-3 py-2">Verified</th>
                    <th className="px-3 py-2">Admin</th>
                    <th className="px-3 py-2">Role</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-t hover:bg-slate-50">
                      <td className="px-3 py-2 text-slate-500">{u.id}</td>
                      <td className="px-3 py-2 text-slate-900">{u.masked_email}</td>
                      <td className="px-3 py-2 text-slate-700">{u.full_name || "—"}</td>
                      <td className="px-3 py-2">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          u.has_active_subscription ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                        }`}>
                          {u.has_active_subscription ? "Yes" : "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={u.is_active}
                          onChange={(e) => toggleUserFlag(u, "is_active", e.target.checked)}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={u.is_verified}
                          onChange={(e) => toggleUserFlag(u, "is_verified", e.target.checked)}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={u.is_admin}
                          onChange={(e) => toggleUserFlag(u, "is_admin", e.target.checked)}
                          // Don't let an admin demote themselves — that
                          // would log them out instantly and the user
                          // would be confused.
                          disabled={u.id === me?.id}
                          title={u.id === me?.id ? "You can't demote yourself" : undefined}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          u.role === "super_admin" ? "bg-purple-100 text-purple-700" :
                          u.role === "admin" ? "bg-blue-100 text-blue-700" :
                          u.role === "moderator" ? "bg-indigo-100 text-indigo-700" :
                          u.role === "finance" ? "bg-amber-100 text-amber-700" :
                          u.role === "support" ? "bg-teal-100 text-teal-700" :
                          "bg-slate-100 text-slate-600"
                        }`}>
                          {u.role || "user"}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {u.is_banned ? (
                          <button
                            onClick={() => unbanUser(u)}
                            className="text-xs px-2 py-1 rounded bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
                          >
                            Banned — lift
                          </button>
                        ) : (
                          <button
                            onClick={() => banUser(u)}
                            className="text-xs px-2 py-1 rounded bg-rose-100 text-rose-700 hover:bg-rose-200"
                          >
                            Ban
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {users.length === 0 && <p className="p-4 text-slate-500 text-center">No users found.</p>}
              {userTotal > USER_PAGE && (
                <div className="flex items-center justify-between p-3 border-t text-sm">
                  <span className="text-slate-500">
                    Showing {userSkip + 1}–{Math.min(userSkip + USER_PAGE, userTotal)} of {userTotal}
                  </span>
                  <div className="flex gap-2">
                    <button
                      disabled={userSkip === 0}
                      onClick={() => reloadUsers(search, Math.max(0, userSkip - USER_PAGE))}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-50"
                    >
                      ← Prev
                    </button>
                    <button
                      disabled={userSkip + USER_PAGE >= userTotal}
                      onClick={() => reloadUsers(search, userSkip + USER_PAGE)}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-50"
                    >
                      Next →
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "grant" && (
          <form onSubmit={submitGrant} className="bg-white rounded-xl shadow-sm p-6 max-w-lg">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Grant a subscription (no payment)</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">User ID</label>
                <input
                  type="number"
                  value={grantUserId}
                  onChange={(e) => setGrantUserId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                />
                <p className="text-xs text-slate-400 mt-1">
                  Find the user ID in the Users tab.
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Plan</label>
                <select
                  value={grantPlan}
                  onChange={(e) => setGrantPlan(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                >
                  {plans.map((p) => (
                    <option key={p.plan_code} value={p.plan_code}>
                      {p.name} ({p.duration_days} days)
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Duration override (days, optional)
                </label>
                <input
                  type="number"
                  value={grantDuration}
                  onChange={(e) => setGrantDuration(e.target.value)}
                  placeholder="Leave blank to use plan default"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                />
              </div>
              <button
                type="submit"
                className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg"
              >
                Grant subscription
              </button>
            </div>
          </form>
        )}

        {tab === "leaderboard" && (
          <div>
            <div className="flex gap-2 mb-3">
              {(["week", "month"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => switchLeaderboard(p)}
                  className={`px-3 py-1.5 text-sm rounded ${
                    period === p
                      ? "bg-purple-600 text-white"
                      : "bg-slate-200 text-slate-700"
                  }`}
                >
                  This {p}
                </button>
              ))}
            </div>
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
                  <tr>
                    <th className="px-3 py-2">Rank</th>
                    <th className="px-3 py-2">User</th>
                    <th className="px-3 py-2 text-right">Total damage</th>
                    <th className="px-3 py-2 text-right">Messages</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((e) => (
                    <tr key={e.user_id} className="border-t">
                      <td className="px-3 py-2 font-bold text-slate-900">#{e.rank}</td>
                      <td className="px-3 py-2">
                        <div className="text-slate-900">{e.full_name || e.masked_email}</div>
                        <div className="text-xs text-slate-500">{e.masked_email}</div>
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{e.total_damage.toFixed(0)}</td>
                      <td className="px-3 py-2 text-right">{e.message_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {leaderboard.length === 0 && (
                <p className="p-4 text-slate-500 text-center">No activity in this period yet.</p>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Top users can be rewarded by granting them a subscription from the Grant tab.
            </p>
          </div>
        )}

        {/* ---- Audit log tab ---- */}
        {tab === "audit" && (
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <input
                value={auditAction}
                onChange={(e) => setAuditAction(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { setAuditSkip(0); loadAudit(); } }}
                placeholder="Filter by action (e.g. login_failed_wrong_password)"
                className="flex-1 min-w-[200px] px-3 py-2 border border-slate-300 rounded-lg"
              />
              <button
                onClick={() => { setAuditSkip(0); loadAudit(); }}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                Search
              </button>
              <button
                onClick={() => { setAuditAction(""); setAuditSkip(0); loadAudit(); }}
                className="px-4 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300"
              >
                Clear
              </button>
            </div>
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
                  <tr>
                    <th className="px-3 py-2">When</th>
                    <th className="px-3 py-2">Action</th>
                    <th className="px-3 py-2">Actor</th>
                    <th className="px-3 py-2">Target</th>
                    <th className="px-3 py-2">IP</th>
                    <th className="px-3 py-2">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="border-t">
                      <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-slate-700">
                        {log.action}
                      </td>
                      <td className="px-3 py-2 text-slate-500">
                        {log.actor_user_id ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-slate-500">
                        {log.target_user_id ?? "—"}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-slate-500">
                        {log.actor_ip ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-500 max-w-xs truncate">
                        {log.details ? JSON.stringify(log.details) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {auditLogs.length === 0 && (
                <p className="p-4 text-slate-500 text-center">No audit log entries match.</p>
              )}
              {auditTotal > AUDIT_PAGE && (
                <div className="flex items-center justify-between p-3 border-t text-sm">
                  <span className="text-slate-500">
                    Showing {auditSkip + 1}–{Math.min(auditSkip + AUDIT_PAGE, auditTotal)} of {auditTotal}
                  </span>
                  <div className="flex gap-2">
                    <button
                      disabled={auditSkip === 0}
                      onClick={() => { setAuditSkip(Math.max(0, auditSkip - AUDIT_PAGE)); }}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-50"
                    >
                      ← Prev
                    </button>
                    <button
                      disabled={auditSkip + AUDIT_PAGE >= auditTotal}
                      onClick={() => setAuditSkip(auditSkip + AUDIT_PAGE)}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-50"
                    >
                      Next →
                    </button>
                  </div>
                </div>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Use the action filter to drill into specific event types (login_failed_*,
              admin_ban_user, account_hard_deleted, etc.).
            </p>
          </div>
        )}

        {/* ---- Feature flags tab ---- */}
        {tab === "flags" && (
          <div>
            <form onSubmit={submitNewFlag} className="mb-4 flex flex-wrap gap-2">
              <input
                value={newFlagKey}
                onChange={(e) => setNewFlagKey(e.target.value)}
                placeholder="flag_key (snake_case)"
                className="flex-1 min-w-[180px] px-3 py-2 border border-slate-300 rounded-lg"
                pattern="[a-z][a-z0-9_]*"
                required
              />
              <input
                value={newFlagDesc}
                onChange={(e) => setNewFlagDesc(e.target.value)}
                placeholder="Optional description"
                className="flex-1 min-w-[200px] px-3 py-2 border border-slate-300 rounded-lg"
              />
              <button type="submit" className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700">
                Add flag (enabled)
              </button>
            </form>
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
                  <tr>
                    <th className="px-3 py-2">Key</th>
                    <th className="px-3 py-2">Description</th>
                    <th className="px-3 py-2">State</th>
                    <th className="px-3 py-2">Updated</th>
                    <th className="px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {flags.map((f) => (
                    <tr key={f.key} className="border-t">
                      <td className="px-3 py-2 font-mono text-xs">{f.key}</td>
                      <td className="px-3 py-2 text-slate-500">{f.description || "—"}</td>
                      <td className="px-3 py-2">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          f.enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                        }`}>
                          {f.enabled ? "ON" : "OFF"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-500">
                        {f.updated_at ? new Date(f.updated_at).toLocaleString() : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => upsertFlag(f.key, !f.enabled)}
                          className={`text-xs px-2 py-1 rounded ${
                            f.enabled
                              ? "bg-rose-100 text-rose-700 hover:bg-rose-200"
                              : "bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
                          }`}
                        >
                          {f.enabled ? "Disable" : "Enable"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {flags.length === 0 && (
                <p className="p-4 text-slate-500 text-center">No flags yet. Add one above.</p>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Currently enforced: <code className="font-mono">history_export_enabled</code> (gates /api/history/export).
              Other flags can be wired into routes from the backend.
            </p>
          </div>
        )}

        {/* ---- Charts tab ---- */}
        {tab === "charts" && (
          <div className="space-y-6">
            <ChartCard title="Signups (last 30 days)" series={signupSeries} color="bg-purple-500" />
            <ChartCard title="Chat volume (last 30 days)" series={chatSeries} color="bg-emerald-500" />
          </div>
        )}

        {/* ---- Monitoring tab (Round 9) ---- */}
        {tab === "monitoring" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">System health</h2>
            {!systemStatus && <p className="text-sm text-slate-500">Loading…</p>}
            {systemStatus && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <MonitorCard label="Overall" value={systemStatus.status} />
                <MonitorCard label="Database" value={systemStatus.database} />
                <MonitorCard label="Cache" value={systemStatus.redis} />
                <MonitorCard label="Queue" value={systemStatus.queue} />
                <MonitorCard label="Sentry" value={systemStatus.sentry} />
                <MonitorCard label="Maintenance" value={systemStatus.maintenance_mode ? "on" : "off"} />
                <MonitorCard label="Version" value={`v${systemStatus.version}`} />
                <MonitorCard label="Build SHA" value={systemStatus.build_sha || "unknown"} />
                <MonitorCard label="Uptime" value={`${Math.floor(systemStatus.uptime_seconds / 60)}m`} />
              </div>
            )}
            <h3 className="text-md font-semibold mt-6">Prometheus /metrics (text)</h3>
            <pre className="text-[10px] bg-slate-900 text-slate-100 rounded p-3 overflow-x-auto max-h-96">{promText || "Loading…"}</pre>
            <p className="text-xs text-slate-500">
              Point your Prometheus scraper at <code className="bg-slate-100 px-1 rounded">/api/v1/system/metrics</code>.
              The metrics endpoint is public so uptime monitors can scrape it without auth.
            </p>
          </div>
        )}

        {/* ---- Contact inbox (Round 9) ---- */}
        {tab === "contact" && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Contact messages</h2>
            {contactMessages.length === 0 && (
              <p className="text-sm text-slate-500">No contact-form submissions yet.</p>
            )}
            <ul className="space-y-2">
              {contactMessages.map((m) => (
                <li
                  key={m.id}
                  className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold">{m.name}</span>
                      <span className="ml-2 text-sm text-slate-500">{m.email}</span>
                    </div>
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        m.status === "new"
                          ? "bg-amber-100 text-amber-800"
                          : m.status === "closed"
                          ? "bg-emerald-100 text-emerald-800"
                          : m.status === "spam"
                          ? "bg-rose-100 text-rose-800"
                          : "bg-sky-100 text-sky-800"
                      }`}
                    >
                      {m.status}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-medium">{m.subject}</div>
                  <div className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{m.message}</div>
                  <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>{new Date(m.created_at).toLocaleString()}</span>
                    <div className="flex gap-2">
                      {(["new", "in_progress", "closed", "spam"] as const).map((s) => (
                        <button
                          key={s}
                          onClick={() =>
                            adminContactApi
                              .updateStatus(m.id, s)
                              .then(() => setContactMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, status: s } : x)))
                              .catch((e) => setMessage("Update failed: " + (e?.detail || "")))
                          }
                          className="rounded border border-slate-200 px-2 py-0.5 text-xs hover:border-purple-400"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ---- Broadcast tab (Round 9) ---- */}
        {tab === "broadcast" && (
          <BroadcastPanel
            onSent={(n) => {
              setMessage(`Broadcast delivered to ${n.delivered_to} user(s).`);
            }}
          />
        )}
      </div>
    </main>
  );
}


function MonitorCard({ label, value }: { label: string; value: string }) {
  const tone =
    /^(ok|active|healthy|on)$/i.test(value)
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : /^(degraded|disabled|inactive|off|down)$/i.test(value)
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : /^(unhealthy|error|fail)/i.test(value)
      ? "bg-rose-50 text-rose-700 border-rose-200"
      : "bg-slate-50 text-slate-700 border-slate-200";
  return (
    <div className={`rounded-lg border p-3 ${tone}`}>
      <div className="text-[10px] uppercase tracking-wide font-semibold">{label}</div>
      <div className="mt-1 text-lg font-bold">{value}</div>
    </div>
  );
}


function BroadcastPanel({ onSent }: { onSent: (r: { delivered_to: number }) => void }) {
  const [target, setTarget] = useState<"all" | "user">("all");
  const [userId, setUserId] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [link, setLink] = useState("");
  const [sending, setSending] = useState(false);

  async function submit() {
    if (!title.trim() || title.trim().length < 3) {
      alert("Title must be at least 3 characters.");
      return;
    }
    if (!body.trim() || body.trim().length < 3) {
      alert("Body must be at least 3 characters.");
      return;
    }
    if (target === "user" && !userId.trim()) {
      alert("Enter a user id to target a single user.");
      return;
    }
    setSending(true);
    try {
      const res = await adminNotificationsApi.broadcast({
        title: title.trim(),
        body: body.trim(),
        link: link.trim() || undefined,
        target: target === "all" ? "all" : userId.trim(),
      });
      onSent(res);
      setTitle("");
      setBody("");
      setLink("");
    } catch (e: any) {
      alert("Broadcast failed: " + (e?.detail || e?.message || ""));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-3 max-w-xl">
      <h2 className="text-lg font-semibold">Broadcast a notification</h2>
      <p className="text-sm text-slate-500">
        Send a notification to every user (or a single one). Users will see it in the
        bell icon and on their Account page.
      </p>
      <div className="flex items-center gap-3 text-sm">
        <label className="flex items-center gap-1">
          <input
            type="radio"
            name="target"
            value="all"
            checked={target === "all"}
            onChange={() => setTarget("all")}
          />
          All users
        </label>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            name="target"
            value="user"
            checked={target === "user"}
            onChange={() => setTarget("user")}
          />
          Single user (id)
        </label>
      </div>
      {target === "user" && (
        <input
          type="text"
          inputMode="numeric"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="User id, e.g. 42"
          className="w-full rounded border border-slate-200 px-3 py-2 text-sm"
        />
      )}
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        maxLength={200}
        className="w-full rounded border border-slate-200 px-3 py-2 text-sm"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Body text"
        maxLength={1000}
        rows={3}
        className="w-full rounded border border-slate-200 px-3 py-2 text-sm"
      />
      <input
        type="text"
        value={link}
        onChange={(e) => setLink(e.target.value)}
        placeholder="Optional link (e.g. /pricing)"
        maxLength={500}
        className="w-full rounded border border-slate-200 px-3 py-2 text-sm"
      />
      <button
        type="button"
        onClick={submit}
        disabled={sending}
        className="rounded bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-700 disabled:opacity-60"
      >
        {sending ? "Sending…" : "Send broadcast"}
      </button>
    </div>
  );
}

function ChartCard({
  title, series, color,
}: { title: string; series: Array<{ date: string; count: number }>; color: string }) {
  const max = Math.max(1, ...series.map((d) => d.count));
  return (
    <div className="bg-white rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-medium text-slate-700 mb-3">{title}</h3>
      {series.length === 0 ? (
        <p className="text-sm text-slate-500">No data yet.</p>
      ) : (
        <div className="flex items-end gap-1 h-32">
          {series.map((d) => (
            <div
              key={d.date}
              className={`flex-1 ${color} rounded-t`}
              style={{ height: `${(d.count / max) * 100}%`, minHeight: d.count > 0 ? "2px" : "0" }}
              title={`${d.date}: ${d.count}`}
            />
          ))}
        </div>
      )}
      <div className="mt-2 flex justify-between text-[10px] text-slate-400">
        <span>{series[0]?.date}</span>
        <span>{series[series.length - 1]?.date}</span>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-white rounded-xl p-4 shadow-sm">
      <div className="text-xs uppercase text-slate-500 tracking-wide">{label}</div>
      <div className="text-2xl font-bold text-slate-900 mt-1">{value}</div>
    </div>
  );
}
