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
  const [showChangePw, setShowChangePw] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");

  useEffect(() => {
    let cancelled = false;
    const token = getAccessToken();
    if (!token) {
      router.push("/login");
      return;
    }
    Promise.all([authApi.me(), subscriptionsApi.my(), paymentsApi.history()])
      .then(([u, s, h]) => {
        if (cancelled) return;
        setUser(u);
        setName(u.full_name || "");
        setGender(u.gender_preference);
        setSubs(s.subscriptions);
        setHistory(h);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e?.status === 401) router.push("/login");
        else setMessage("Failed to load account: " + (e?.detail || ""));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [router]);

  async function saveProfile() {
    setMessage("");
    // Trim the name; reject whitespace-only as a "no name" (we treat
    // empty name as "clear it" which is allowed, but spaces-only is
    // not).
    const trimmed = name.trim();
    if (name.length > 0 && trimmed.length === 0) {
      setMessage("Name can't be only whitespace.");
      return;
    }
    try {
      const u = await authApi.updateMe({ full_name: trimmed, gender_preference: gender });
      setUser(u);
      setEditing(false);
      setMessage("Profile updated ✅");
    } catch (e: any) {
      setMessage(e?.detail || "Update failed");
    }
  }

  async function changePassword() {
    if (newPw.length < 8) {
      setMessage("New password must be at least 8 characters");
      return;
    }
    if (!currentPw) {
      setMessage("Enter your current password.");
      return;
    }
    if (newPw === currentPw) {
      setMessage("New password must be different from the current one.");
      return;
    }
    setMessage("");
    try {
      await authApi.changePassword({ current_password: currentPw, new_password: newPw });
      setMessage("Password updated ✅ Other sessions signed out.");
      setCurrentPw("");
      setNewPw("");
      setShowChangePw(false);
    } catch (e: any) {
      setMessage(e?.detail || "Password change failed");
    }
  }

  async function cancelSub() {
    if (!confirm("Cancel your subscription? You will keep access until the period ends.")) return;
    setMessage("");
    try {
      const r = await subscriptionsApi.cancel();
      setMessage("Cancelled ✅ Access until " + new Date(r.current_period_end).toLocaleDateString());
      // The second fetch (refresh subscription list) is best-effort.
      // If it fails, the user still sees the success message — the
      // header was already updated via emitAuthRefresh inside
      // subscriptionsApi.cancel.
      try {
        const s = await subscriptionsApi.my();
        setSubs(s.subscriptions);
      } catch { /* best-effort */ }
    } catch (e: any) {
      setMessage(e?.detail || "Cancel failed");
    }
  }

  async function logout() {
    await authApi.logout();
  }

  if (loading) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-muted">
        <div className="text-center">
          <div className="text-4xl animate-pulse">🔥</div>
          <p className="mt-3 text-sm">Loading account…</p>
        </div>
      </div>
    );
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
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="font-display text-3xl font-bold">Your Account</h1>
        <button
          onClick={logout}
          className="btn-ghost text-sm"
        >
          Sign out
        </button>
      </header>

      {message && (
        <div
          role="status"
          className="rounded-lg border border-accent/40 bg-accent/10 p-3 text-sm text-accent"
        >
          {message}
        </div>
      )}

      {/* Profile */}
      <section className="card">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold">Profile</h2>
          {!editing && (
            <button onClick={() => setEditing(true)} className="text-sm text-accent-3 hover:underline">
              Edit
            </button>
          )}
        </div>
        {editing ? (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-muted">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input"
                maxLength={255}
                aria-label="Display name"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-muted">Roaster preference</label>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className="input"
                aria-label="Roaster voice preference"
              >
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="neutral">Neutral</option>
              </select>
            </div>
            <div className="flex gap-2">
              <button onClick={saveProfile} className="btn-primary text-sm">
                Save
              </button>
              <button onClick={() => setEditing(false)} className="btn-ghost text-sm">
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <dt className="text-muted">Email</dt>
            <dd>{user.email}</dd>
            <dt className="text-muted">Name</dt>
            <dd>{user.full_name || "—"}</dd>
            <dt className="text-muted">Roaster</dt>
            <dd className="capitalize">{user.gender_preference}</dd>
            <dt className="text-muted">Free messages used</dt>
            <dd>{user.free_messages_used} / 5</dd>
          </dl>
        )}
      </section>

      {/* Change password (always visible for quick access) */}
      <section className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold">Security</h2>
          {!showChangePw && (
            <button
              onClick={() => setShowChangePw(true)}
              className="text-sm text-accent-3 hover:underline"
            >
              Change password
            </button>
          )}
        </div>
        {showChangePw ? (
          <div className="space-y-3">
            <input
              type="password"
              placeholder="Current password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              className="input"
              autoComplete="current-password"
              aria-label="Current password"
            />
            <input
              type="password"
              placeholder="New password (8+ characters)"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              className="input"
              autoComplete="new-password"
              minLength={8}
              aria-label="New password"
            />
            <div className="flex gap-2">
              <button onClick={changePassword} className="btn-primary text-sm">
                Update password
              </button>
              <button
                onClick={() => { setShowChangePw(false); setCurrentPw(""); setNewPw(""); }}
                className="btn-ghost text-sm"
              >
                Cancel
              </button>
            </div>
            <p className="text-xs text-muted">
              Changing your password signs out all other devices. You&apos;ll stay signed in here.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted">
            Last changed: never recorded. Update regularly.
          </p>
        )}
      </section>

      {/* Subscription */}
      <section className="card">
        <h2 className="mb-4 font-display text-xl font-semibold">Subscription</h2>
        {inEffect ? (
          <div className="space-y-2 text-sm">
            <p>
              {cancellationPending ? (
                <span className="mr-2 inline-block rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-300">
                  Cancellation pending
                </span>
              ) : (
                <span className="mr-2 inline-block rounded bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-300">
                  active
                </span>
              )}
              <strong>{inEffect.plan_name}</strong>
            </p>
            <p className="text-muted">
              {inEffect.current_period_end
                ? `${cancellationPending ? "Access until" : "Active until"} ${new Date(inEffect.current_period_end).toLocaleDateString()}`
                : "—"}
            </p>
            {inEffect.admin_granted && (
              <p className="text-xs text-amber-300">
                🎁 This subscription was granted to you (free).
              </p>
            )}
            {!cancellationPending && (
              <button
                onClick={cancelSub}
                className="btn-ghost mt-3 text-sm text-accent"
              >
                Cancel subscription
              </button>
            )}
          </div>
        ) : anySub ? (
          <div>
            <p className="mb-3 text-muted">
              Your <strong>{anySub.plan_name}</strong> subscription is{" "}
              <span className="capitalize">{anySub.status}</span>
              {anySub.current_period_end && (
                <>
                  {" "}(expired {new Date(anySub.current_period_end).toLocaleDateString()})
                </>
              )}.
            </p>
            <a href="/pricing" className="btn-primary text-sm">
              See plans
            </a>
          </div>
        ) : (
          <div>
            <p className="mb-3 text-muted">You don&apos;t have an active subscription.</p>
            <a href="/pricing" className="btn-primary text-sm">
              See plans
            </a>
          </div>
        )}
      </section>

      {/* Payment history */}
      <section className="card">
        <h2 className="mb-4 font-display text-xl font-semibold">Payment history</h2>
        {history.length === 0 ? (
          <p className="text-sm text-muted">No payments yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b text-left text-muted">
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
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        p.status === "captured"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-surface text-muted"
                      }`}
                    >
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
  );
}
