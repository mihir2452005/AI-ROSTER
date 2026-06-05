"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { authApi } from "../../lib/auth-api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pending) return;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      toast.error("Enter a valid email");
      return;
    }
    setPending(true);
    try {
      await authApi.forgotPassword(email);
      // Always show success — backend returns 200 even for unknown
      // addresses to prevent email enumeration.
      setDone(true);
      toast.success("If that email exists, a reset link has been sent");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed";
      toast.error(msg);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mx-auto max-w-md card">
      <h1 className="font-display text-2xl font-bold gradient-text">Forgot password</h1>
      <p className="mt-2 text-sm text-muted">
        Enter your email and we&apos;ll send a reset link if the account exists.
      </p>
      {done ? (
        <div className="mt-4 rounded-lg border border-border bg-surface/50 p-4 text-sm">
          <p className="text-text">Check your inbox.</p>
          <p className="mt-2 text-muted">
            If you don&apos;t see the email in a few minutes, check your spam folder.
          </p>
          <Link href="/login" className="btn-ghost mt-4 inline-block">Back to login</Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-3">
          <div>
            <label className="mb-1 block text-sm text-muted" htmlFor="fp-email">Email</label>
            <input
              id="fp-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              autoComplete="email"
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={pending}>
            {pending ? "Sending…" : "Send reset link"}
          </button>
          <p className="text-center text-sm text-muted">
            Remembered it? <Link href="/login" className="text-accent-2 hover:underline">Log in</Link>
          </p>
        </form>
      )}
    </div>
  );
}
