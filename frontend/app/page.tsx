"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MODES, PERSONALITIES, type Personality, type RoastMode } from "@/lib/types";
import { api, friendlyError } from "@/lib/api";
import {
  authApi,
  clearTokens,
  getAccessToken,
  getCachedUser,
  getStoredTokenVersion,
  cacheUser,
  type User,
} from "@/lib/auth-api";

export default function HomePage() {
  const router = useRouter();
  const [mode, setMode] = useState<RoastMode>("savage");
  const [personality, setPersonality] = useState<Personality>("savage_one");
  const [username, setUsername] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If the user is logged in, prefill their saved name and use their
  // saved roaster-gender preference to drive personalized roast generation.
  // We also honour the saved `favorite_mode` / `favorite_personality`
  // (set in /account) so the user doesn't have to re-pick every time.
  //
  // We also cross-check the server's `token_version` against the
  // cached one: if they don't match, the token has been revoked on
  // another device (password change, admin deactivation, explicit
  // logout) and we force a fresh login. This matches the behaviour of
  // HeaderAuth.
  useEffect(() => {
    if (!getAccessToken()) return;
    const cached = getCachedUser();
    const cachedVer = getStoredTokenVersion();
    authApi
      .me()
      .then((u) => {
        if (cached && cachedVer !== 0 && u.token_version !== cachedVer) {
          // Token revoked elsewhere. Drop the stale state and let the
          // header render the signed-out UI on the next render.
          clearTokens();
          setUser(null);
          return;
        }
        cacheUser(u);
        setUser(u);
        if (u.full_name) setUsername(u.full_name);
        // Apply favorites only if they're valid for the current
        // (typed) RoastMode/Personality unions. We compare against the
        // MODES and PERSONALITIES lists so a stale favorite from a
        // future schema version doesn't crash the picker.
        if (u.favorite_mode) {
          const valid = (MODES.find((m) => m.value === u.favorite_mode));
          if (valid) setMode(valid.value);
        }
        if (u.favorite_personality) {
          const valid = PERSONALITIES.find((p) => p.value === u.favorite_personality);
          if (valid) setPersonality(valid.value);
        }
      })
      .catch(() => { /* not logged in - keep going */ });
  }, []);

  async function startSession() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.startSession({
        mode,
        personality,
        username: username.trim() || undefined,
        roaster_gender: user?.gender_preference || undefined,
      });
      router.push(`/chat/${res.session_id}`);
    } catch (e) {
      setError(friendlyError(e));
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-10 md:grid-cols-2 md:gap-16 md:py-10">
      <section className="flex flex-col justify-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <span className="pill mb-4">
            <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
            <span>The Internet's Most Ruthless AI</span>
          </span>
          <h1 className="font-display text-5xl font-extrabold leading-tight md:text-7xl">
            Get roasted by an AI with <span className="gradient-text">zero chill.</span>
          </h1>
          <p className="mt-5 max-w-prose text-lg text-muted">
            Pick a mode, pick a personality, and watch your self-esteem get taken behind the
            woodshed. Screenshot-worthy burns. Shareable sessions. Zero remorse.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          className="mt-10"
        >
          <div className="card">
            <label className="mb-2 block text-sm font-medium text-muted">
              Your name <span className="text-muted/60">(optional â€” the AI will use it against you)</span>
            </label>
            <input
              type="text"
              className="input"
              placeholder="e.g. Alex"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              maxLength={64}
            />
            <button
              onClick={startSession}
              disabled={busy}
              className="btn-primary mt-4 w-full text-base"
            >
              {busy ? "Warming up the roasterâ€¦" : "Start a roast session 🔥"}
            </button>
            {error && (
              <p className="mt-3 text-sm text-accent">{error}</p>
            )}
          </div>
        </motion.div>
      </section>

      <section className="space-y-6">
        <div>
          <h2 className="mb-3 font-display text-2xl font-bold">Pick a roast mode</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {MODES.map((m) => (
              <button
                key={m.value}
                onClick={() => setMode(m.value)}
                className={`group flex items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                  mode === m.value
                    ? "border-accent bg-accent/10"
                    : "border-border bg-surface/50 hover:border-accent/40"
                }`}
              >
                <span className="text-2xl">{m.emoji}</span>
                <div className="min-w-0">
                  <div className="font-semibold">{m.label}</div>
                  <div className="text-xs text-muted">{m.description}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-3 font-display text-2xl font-bold">Pick a personality</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {PERSONALITIES.map((p) => (
              <button
                key={p.value}
                onClick={() => setPersonality(p.value)}
                className={`group flex items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                  personality === p.value
                    ? "border-accent-2 bg-accent-2/10"
                    : "border-border bg-surface/50 hover:border-accent-2/40"
                }`}
              >
                <span className="text-2xl">{p.emoji}</span>
                <div className="min-w-0">
                  <div className="font-semibold">{p.label}</div>
                  <div className="text-xs text-muted">{p.description}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
