"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  adminApi,
  authApi,
  paymentsApi,
  getAccessToken,
  type AdminUser,
  type AdminStats,
  type LeaderboardEntry,
  type Plan,
  type User,
} from "../../lib/auth-api";

type Tab = "stats" | "users" | "grant" | "leaderboard";

export default function AdminPage() {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);
  const [tab, setTab] = useState<Tab>("stats");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [period, setPeriod] = useState<"week" | "month">("week");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [grantUserId, setGrantUserId] = useState("");
  const [grantPlan, setGrantPlan] = useState("pro");
  const [grantDuration, setGrantDuration] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    authApi
      .me()
      .then((u) => {
        if (!u.is_admin) {
          setMessage("Admins only. Redirecting…");
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

  function reloadUsers(q?: string) {
    adminApi
      .listUsers({ search: q, limit: 50 })
      .then((r) => {
        setUsers(r.users);
        setUserTotal(r.total);
      })
      .catch((e) => setMessage("Search failed: " + (e?.detail || "")));
  }

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
    return <main className="min-h-screen flex items-center justify-center text-slate-500">Loading admin…</main>;
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
          <a href="/" className="text-sm text-purple-600 hover:underline">← Back to app</a>
        </header>

        {message && (
          <div className="mb-4 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-800 text-sm">
            {message}
          </div>
        )}

        <nav className="flex gap-2 mb-6 border-b border-slate-200">
          {(["stats", "users", "grant", "leaderboard"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t
                  ? "border-purple-600 text-purple-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t === "stats" ? "Stats" : t === "users" ? `Users (${userTotal})` : t === "grant" ? "Grant" : "Leaderboard"}
            </button>
          ))}
        </nav>

        {tab === "stats" && stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Stat label="Total users" value={stats.total_users} />
            <Stat label="Active users" value={stats.active_users} />
            <Stat label="Active subs" value={stats.active_subscriptions} />
            <Stat label="Total payments" value={stats.total_payments} />
            <Stat label="Revenue" value={`₹${(stats.total_revenue_paise / 100).toFixed(0)}`} />
          </div>
        )}

        {tab === "users" && (
          <div>
            <input
              type="text"
              placeholder="Search by email or name…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                reloadUsers(e.target.value);
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
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {users.length === 0 && <p className="p-4 text-slate-500 text-center">No users found.</p>}
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
      </div>
    </main>
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
