"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { authApi } from "../../lib/auth-api";

function ResetPasswordInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [showReqs, setShowReqs] = useState(false);

  useEffect(() => {
    if (!token) {
      // Defer to render so the toast isn't lost in SSR-skip mode.
      setTimeout(() => toast.error("Missing or invalid reset token"), 0);
    }
  }, [token]);

  const valid = password.length >= 8 && password === confirm && token.length > 0;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pending || !valid) return;
    setPending(true);
    try {
      await authApi.resetPassword(token, password);
      toast.success("Password reset. Logging you in…");
      // Force login flow: tokens were invalidated server-side.
      router.push("/login");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Reset failed";
      toast.error(msg);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mx-auto max-w-md card">
      <h1 className="font-display text-2xl font-bold gradient-text">Set a new password</h1>
      {!token ? (
        <p className="mt-4 text-sm text-accent">
          This page expects a reset token in the URL. Use the link from your reset email.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-3">
          <div>
            <label className="mb-1 block text-sm text-muted" htmlFor="rp-new">New password</label>
            <input
              id="rp-new"
              type="password"
              required
              value={password}
              onFocus={() => setShowReqs(true)}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              autoComplete="new-password"
              minLength={8}
            />
            {showReqs && (
              <p className="mt-1 text-xs text-muted">At least 8 characters.</p>
            )}
          </div>
          <div>
            <label className="mb-1 block text-sm text-muted" htmlFor="rp-confirm">Confirm new password</label>
            <input
              id="rp-confirm"
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="input"
              autoComplete="new-password"
              minLength={8}
            />
            {confirm && confirm !== password && (
              <p className="mt-1 text-xs text-accent">Passwords do not match.</p>
            )}
          </div>
          <button type="submit" className="btn-primary w-full" disabled={!valid || pending}>
            {pending ? "Resetting…" : "Reset password"}
          </button>
          <p className="text-center text-sm text-muted">
            <Link href="/login" className="text-accent-2 hover:underline">Back to login</Link>
          </p>
        </form>
      )}
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="text-muted">Loading…</div>}>
      <ResetPasswordInner />
    </Suspense>
  );
}
