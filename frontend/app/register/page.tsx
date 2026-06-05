"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi } from "../../lib/auth-api";
import { safeReturnPath } from "../../lib/security";

type Gender = "male" | "female" | "neutral";

export default function RegisterPage() {
  return (
    <Suspense fallback={
      <main className="min-h-screen flex items-center justify-center text-slate-500">Loading…</main>
    }>
      <RegisterPageInner />
    </Suspense>
  );
}

function RegisterPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  // Validate the return path to prevent open-redirect phishing.
  const returnTo = safeReturnPath(params?.get("return") || "/", "/");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [gender, setGender] = useState<Gender>("neutral");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    // Trim the full name; reject if it's whitespace-only.
    const trimmedName = fullName.trim();
    if (fullName.length > 0 && trimmedName.length === 0) {
      setError("Name can't be only whitespace.");
      return;
    }
    setLoading(true);
    try {
      // authApi.register already stores the tokens in sessionStorage
      // (see lib/auth-api.ts:187-200). No need to call setTokens again.
      await authApi.register({
        email,
        password,
        full_name: trimmedName || undefined,
        gender_preference: gender,
      });
      router.push(returnTo);
    } catch (err: any) {
      setError(err?.detail || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-700 px-4 py-8">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Get started</h1>
        <p className="text-slate-500 mb-6">Create an account and choose who roasts you.</p>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Full name (optional)</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              maxLength={255}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

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
            <label className="block text-sm font-medium text-slate-700 mb-1">Password (min 8 chars)</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              autoComplete="new-password"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Who should roast you?
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(["female", "male", "neutral"] as const).map((g) => (
                <button
                  type="button"
                  key={g}
                  onClick={() => setGender(g)}
                  className={`py-2 px-3 rounded-lg text-sm font-medium border-2 transition ${
                    gender === g
                      ? "border-purple-600 bg-purple-50 text-purple-700"
                      : "border-slate-200 text-slate-600 hover:border-slate-300"
                  }`}
                >
                  {g === "female" ? "👩 Female" : g === "male" ? "👨 Male" : "🧑 Neutral"}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              You can change this later in settings.
            </p>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:opacity-90 disabled:opacity-50 transition"
          >
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          Already have an account?{" "}
          <Link href="/login" className="text-purple-600 hover:underline font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
