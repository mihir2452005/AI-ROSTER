"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  authApi,
  subscriptionsApi,
  paymentsApi,
  getAccessToken,
  type User,
  type Subscription,
  type Payment,
} from "../../lib/auth-api";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [history, setHistory] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [gender, setGender] = useState("neutral");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      router.push("/login");
      return;
    }
    Promise.all([authApi.me(), subscriptionsApi.my(), paymentsApi.history()])
      .then(([u, s, h]) => {
        setUser(u);
        setName(u.full_name || "");
        setGender(u.gender_preference);
        setSubs(s.subscriptions);
        setHistory(h);
      })
      .catch((e) => {
        if (e?.status === 401) router.push("/login");
        else setMessage("Failed to load account: " + (e?.detail || ""));
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function saveProfile() {
    setMessage("");
    try {
      const u = await authApi.updateMe({ full_name: name, gender_preference: gender });
      setUser(u);
      setEditing(false);
      setMessage("Profile updated ✅");
    } catch (e: any) {
      setMessage(e?.detail || "Update failed");
    }
  }

  async function cancelSub() {
    if (!confirm("Cancel your subscription? You will keep access until the period ends.")) return;
    setMessage("");
    try {
      const r = await subscriptionsApi.cancel();
      setMessage("Cancelled ✅ Access until " + new Date(r.current_period_end).toLocaleDateString());
      const s = await subscriptionsApi.my();
      setSubs(s.subscriptions);
    } catch (e: any) {
      setMessage(e?.detail || "Cancel failed");
    }
  }

  function logout() {
    authApi.logout();
  }

  if (loading) {
    return <main className="min-h-screen flex items-center justify-center text-slate-500">Loading…</main>;
  }
  if (!user) return null;

  // "Currently in effect" means: status=active AND period_end > now. This
  // matches the backend's `has_active_subscription` rule. The "Cancel
  // subscription" button only renders when the user hasn't already
  // requested cancellation (cancel_at_period_end).
  const now = Date.now();
  const inEffect = subs.find(
    (s) => s.status === "active" && s.current_period_end && new Date(s.current_period_end).getTime() > now
  );
  // Sub being cancelled this period (status still "active" but
  // cancel_at_period_end is set) — show "Cancellation pending" badge
  // and hide the cancel button.
  const cancellationPending = subs.find(
    (s) => s.status === "active" && s.cancel_at_period_end
  );
  // Any subscription at all, even expired/cancelled.
  const anySub = subs[0];

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <header className="flex justify-between items-center">
          <h1 className="text-3xl font-bold text-slate-900">Your Account</h1>
          <button
            onClick={logout}
            className="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900"
          >
            Sign out
          </button>
        </header>

        {message && (
          <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-800 text-sm">
            {message}
          </div>
        )}

        {/* Profile */}
        <section className="bg-white rounded-xl p-6 shadow-sm">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-slate-900">Profile</h2>
            {!editing && (
              <button onClick={() => setEditing(true)} className="text-sm text-purple-600 hover:underline">
                Edit
              </button>
            )}
          </div>
          {editing ? (
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Roaster preference</label>
                <select
                  value={gender}
                  onChange={(e) => setGender(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                >
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                  <option value="neutral">Neutral</option>
                </select>
              </div>
              <div className="flex gap-2">
                <button onClick={saveProfile} className="px-4 py-2 bg-purple-600 text-white rounded-lg">
                  Save
                </button>
                <button onClick={() => setEditing(false)} className="px-4 py-2 text-slate-600">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <dt className="text-slate-500">Email</dt>
              <dd className="text-slate-900">{user.email}</dd>
              <dt className="text-slate-500">Name</dt>
              <dd className="text-slate-900">{user.full_name || "—"}</dd>
              <dt className="text-slate-500">Roaster</dt>
              <dd className="text-slate-900 capitalize">{user.gender_preference}</dd>
              <dt className="text-slate-500">Free messages used</dt>
              <dd className="text-slate-900">{user.free_messages_used}</dd>
            </dl>
          )}
        </section>

        {/* Subscription */}
        <section className="bg-white rounded-xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Subscription</h2>
          {inEffect ? (
            <div className="space-y-2 text-sm">
              <p>
                {cancellationPending ? (
                  <span className="inline-block px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-700 mr-2">
                    Cancellation pending
                  </span>
                ) : (
                  <span className="inline-block px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-700 mr-2">
                    active
                  </span>
                )}
                <strong>{inEffect.plan_name}</strong>
              </p>
              <p className="text-slate-600">
                {inEffect.current_period_end
                  ? `${cancellationPending ? "Access until" : "Active until"} ${new Date(inEffect.current_period_end).toLocaleDateString()}`
                  : "—"}
              </p>
              {inEffect.admin_granted && (
                <p className="text-xs text-amber-600">
                  🎁 This subscription was granted to you (free).
                </p>
              )}
              {!cancellationPending && (
                <button
                  onClick={cancelSub}
                  className="mt-3 px-4 py-1.5 text-sm text-red-600 hover:bg-red-50 rounded"
                >
                  Cancel subscription
                </button>
              )}
            </div>
          ) : anySub ? (
            <div>
              <p className="text-slate-600 mb-3">
                Your <strong>{anySub.plan_name}</strong> subscription is{" "}
                <span className="capitalize">{anySub.status}</span>
                {anySub.current_period_end && (
                  <>
                    {" "}(expired {new Date(anySub.current_period_end).toLocaleDateString()})
                  </>
                )}.
              </p>
              <a
                href="/pricing"
                className="inline-block px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg"
              >
                See plans
              </a>
            </div>
          ) : (
            <div>
              <p className="text-slate-600 mb-3">You don&apos;t have an active subscription.</p>
              <a
                href="/pricing"
                className="inline-block px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg"
              >
                See plans
              </a>
            </div>
          )}
        </section>

        {/* Payment history */}
        <section className="bg-white rounded-xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Payment history</h2>
          {history.length === 0 ? (
            <p className="text-sm text-slate-500">No payments yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500 border-b">
                <tr>
                  <th className="pb-2">Date</th>
                  <th className="pb-2">Description</th>
                  <th className="pb-2 text-right">Amount</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((p) => (
                  <tr key={p.id} className="border-b last:border-0">
                    <td className="py-2">{new Date(p.created_at).toLocaleDateString()}</td>
                    <td className="py-2">{p.description || "—"}</td>
                    <td className="py-2 text-right">₹{(p.amount / 100).toFixed(2)}</td>
                    <td className="py-2">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        p.status === "captured" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"
                      }`}>
                        {p.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </main>
  );
}
