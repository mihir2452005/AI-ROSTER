"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi } from "../../lib/auth-api";
import { safeReturnPath } from "../../lib/security";

export default function LoginPage() {
  // `useSearchParams` requires a Suspense boundary in Next.js 14
  // app-router builds; the inner component does the real work and
  // the outer component just wraps it for streaming.
  return (
    <Suspense fallback={
      <main className="min-h-screen flex items-center justify-center text-slate-500">Loadingâ€¦</main>
    }>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  // `?return=/pricing` is set by the pricing page when an anonymous
  // visitor clicks "Get Pro". Bring them back here after login.
  // We validate the return path is a same-origin relative URL â€”
  // otherwise an attacker could craft a phishing link
  // `?return=https://evil.com` and we'd navigate to it.
  const rawReturn = params?.get("return") || "/";
  const safeReturn = safeReturnPath(rawReturn, "/");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // authApi.login already stores the tokens in sessionStorage
      // (see lib/auth-api.ts:202-212). No need to call setTokens again.
      await authApi.login({ email, password });
      router.push(safeReturn);
    } catch (err: any) {
      setError(err?.detail || "Login failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-700 px-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Welcome back</h1>
        <p className="text-slate-500 mb-6">Sign in to continue roasting (and being roasted).</p>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              autoComplete="email"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              autoComplete="current-password"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:opacity-90 disabled:opacity-50 transition"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          New here?{" "}
          <Link href="/register" className="text-purple-600 hover:underline font-medium">
            Create an account
          </Link>
        </p>
      </div>
    </main>
  );
}
