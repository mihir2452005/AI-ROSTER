"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  authApi,
  subscriptionsApi,
  paymentsApi,
  notificationsApi,
  getAccessToken,
  type User,
  type Subscription,
  type Payment,
  type ActivityItem,
} from "../../lib/auth-api";

const AVATAR_MAX_BYTES = 2 * 1024 * 1024; // 2 MB

const ROSTASTE_MODES = ["savage", "programmer", "gamer", "student", "startup", "general", "corporate", "friendly"] as const;
const PERSONALITIES = ["sarcastic", "savage", "wholesome", "dry", "nerdy"] as const;

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
  const [resending, setResending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
    const trimmed = name.trim();
    if (name.length > 0 && trimmed.length === 0) {
      setMessage("Name can't be only whitespace.");
      return;
    }
    try {
      const u = await authApi.updateMe({ full_name: trimmed, gender_preference: gender });
      setUser(u);
      setEditing(false);
      toast.success("Profile updated");
      setMessage("");
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
      toast.success("Password updated. Other sessions signed out.");
      setCurrentPw("");
      setNewPw("");
      setShowChangePw(false);
    } catch (e: any) {
      setMessage(e?.detail || "Password change failed");
    }
  }

  async function cancelSub() {
    if (!confirm("Cancel your subscription? You will keep access until the period ends.")) return;
    try {
      const r = await subscriptionsApi.cancel();
      toast.success("Cancelled — access until " + new Date(r.current_period_end).toLocaleDateString());
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

  async function onAvatarFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error("Please choose an image file");
      return;
    }
    if (file.size > AVATAR_MAX_BYTES) {
      toast.error("Avatar must be 2 MB or smaller");
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      const data_uri = String(reader.result);
      try {
        const r = await authApi.uploadAvatar(data_uri);
        // Refresh user so header (which reads cached user) sees new avatar
        const fresh = await authApi.me();
        setUser(fresh);
        toast.success("Avatar updated");
        // touch r so it isn't flagged as unused
        void r;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        toast.error(msg);
      }
    };
    reader.onerror = () => toast.error("Could not read file");
    reader.readAsDataURL(file);
  }

  async function setFavMode(mode: string) {
    try {
      const u = await authApi.setFavorites({ favorite_mode: mode });
      setUser(u);
      toast.success("Favorite mode saved");
    } catch (e) {
      toast.error("Could not save favorite");
    }
  }
  async function setFavPersonality(p: string) {
    try {
      const u = await authApi.setFavorites({ favorite_personality: p });
      setUser(u);
      toast.success("Favorite personality saved");
    } catch (e) {
      toast.error("Could not save favorite");
    }
  }

  async function resendVerification() {
    if (resending) return;
    setResending(true);
    try {
      await authApi.sendVerification();
      toast.success("Verification email sent — check your inbox");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not send";
      toast.error(msg);
    } finally {
      setResending(false);
    }
  }

  async function deleteAccount() {
    if (!user) return;
    const confirmText = prompt(
      "This will soft-delete your account. Your data will be permanently removed after 30 days.\n\nType DELETE to confirm:",
    );
    if (confirmText !== "DELETE") return;
    try {
      await authApi.deleteMe();
      toast.success("Account scheduled for deletion. Signing you out…");
      // Clear local tokens and bounce to home — soft-delete makes the
      // current JWT invalid (token_version bump).
      setTimeout(() => {
        if (typeof window !== "undefined") window.location.href = "/";
      }, 1200);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      toast.error(msg);
    }
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

  const now = Date.now();
  const inEffect = subs.find(
    (s) => s.status === "active" && s.current_period_end && new Date(s.current_period_end).getTime() > now
  );
  const cancellationPending = subs.find(
    (s) => s.status === "active" && s.cancel_at_period_end
  );
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

      {/* Email verification banner */}
      {!user.is_verified && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="text-amber-300">Your email isn&apos;t verified yet.</span>
            <button
              className="btn-ghost text-xs"
              onClick={resendVerification}
              disabled={resending}
            >
              {resending ? "Sending…" : "Resend verification email"}
            </button>
          </div>
        </div>
      )}

      {/* Banned banner */}
      {user.is_banned && (
        <div className="rounded-lg border border-accent/60 bg-accent/15 p-3 text-sm">
          <p className="font-semibold text-accent">This account is suspended.</p>
          {user.ban_reason && (
            <p className="mt-1 text-muted">Reason: {user.ban_reason}</p>
          )}
          {user.banned_at && (
            <p className="mt-1 text-xs text-muted">
              Suspended on {new Date(user.banned_at).toLocaleString()}.
            </p>
          )}
          <p className="mt-2 text-xs text-muted">
            Contact support if you believe this is a mistake.
          </p>
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

        {/* Avatar */}
        <div className="mb-4 flex items-center gap-4">
          {user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatar_url}
              alt="Your avatar"
              className="h-16 w-16 rounded-full border border-border object-cover"
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-surface text-xl font-bold text-muted">
              {(user.full_name || user.email).slice(0, 1).toUpperCase()}
            </div>
          )}
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onAvatarFile}
            />
            <button
              className="btn-ghost text-sm"
              onClick={() => fileInputRef.current?.click()}
            >
              {user.avatar_url ? "Replace avatar" : "Upload avatar"}
            </button>
            <p className="mt-1 text-xs text-muted">PNG/JPG, up to 2 MB.</p>
          </div>
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
            <dd>
              {user.email}
              {user.is_verified && (
                <span className="ml-2 inline-block rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] text-emerald-300">
                  verified
                </span>
              )}
            </dd>
            <dt className="text-muted">Name</dt>
            <dd>{user.full_name || "—"}</dd>
            <dt className="text-muted">Roaster</dt>
            <dd className="capitalize">{user.gender_preference}</dd>
            <dt className="text-muted">Free messages used</dt>
            <dd>{user.free_messages_used} / 5</dd>
            {user.last_login_at && (
              <>
                <dt className="text-muted">Last sign-in</dt>
                <dd>{new Date(user.last_login_at).toLocaleString()}</dd>
              </>
            )}
          </dl>
        )}
      </section>

      {/* Favorites */}
      <section className="card">
        <h2 className="mb-3 font-display text-xl font-semibold">Favorites</h2>
        <p className="mb-3 text-xs text-muted">
          These pre-fill on the chat screen. They only affect your defaults.
        </p>
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-sm text-muted">Favorite roast mode</div>
            <div className="flex flex-wrap gap-2">
              {ROSTASTE_MODES.map((m) => (
                <button
                  key={m}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    user.favorite_mode === m
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border bg-surface text-muted hover:text-text"
                  }`}
                  onClick={() => setFavMode(m)}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1 text-sm text-muted">Favorite personality</div>
            <div className="flex flex-wrap gap-2">
              {PERSONALITIES.map((p) => (
                <button
                  key={p}
                  className={`rounded-full border px-3 py-1 text-xs capitalize ${
                    user.favorite_personality === p
                      ? "border-accent-2 bg-accent-2/10 text-accent-2"
                      : "border-border bg-surface text-muted hover:text-text"
                  }`}
                  onClick={() => setFavPersonality(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>
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

      {/* Recent Activity */}
      <ActivitySection />

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

      {/* Danger zone */}
      <section className="card border-accent/40">
        <h2 className="mb-2 font-display text-xl font-semibold text-accent">Danger zone</h2>
        <p className="mb-3 text-sm text-muted">
          Deleting your account is permanent after a 30-day grace period. During the grace
          period, sign back in with the same email to restore it.
        </p>
        <button
          onClick={deleteAccount}
          className="rounded-lg border border-accent/50 px-3 py-1.5 text-sm text-accent hover:bg-accent/10"
        >
          Delete my account
        </button>
      </section>
    </div>
  );
}


function ActivitySection() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    notificationsApi
      .activity({ limit: 20 })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || "Couldn't load activity");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="card">
      <h2 className="mb-3 font-display text-xl font-semibold">Recent Activity</h2>
      {loading && <p className="text-sm text-muted">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="text-sm text-muted">No activity yet. Actions like logging in, sharing a roast, or starting a subscription will show up here.</p>
      )}
      {!loading && items.length > 0 && (
        <ul className="divide-y divide-white/5">
          {items.map((it) => (
            <li key={it.id} className="flex items-start gap-3 py-2 text-sm">
              <span aria-hidden className="w-6 text-center text-base">
                {it.icon}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-fg">{it.label}</div>
                <div className="text-xs text-muted">
                  {new Date(it.created_at).toLocaleString()}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

