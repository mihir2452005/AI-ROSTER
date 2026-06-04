"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api, friendlyError } from "@/lib/api";
import type { SessionStateResponse } from "@/lib/types";

interface Props {
  sessionId: string;
}

export default function ShareClient({ sessionId }: Props) {
  const [session, setSession] = useState<SessionStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.getSession(sessionId);
        if (!cancelled) setSession(s);
      } catch (e) {
        if (!cancelled) setError(friendlyError(e));
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  if (error) {
    return (
      <div className="card mx-auto max-w-2xl text-center">
        <h1 className="font-display text-2xl font-bold">Session not found</h1>
        <p className="mt-2 text-muted">{error}</p>
        <a href="/" className="btn-primary mt-6 inline-flex">Start your own session</a>
      </div>
    );
  }

  if (!session) {
    return <div className="text-center text-muted">Loading…</div>;
  }

  return (
    <article className="mx-auto max-w-3xl">
      <header className="mb-6 text-center">
        <span className="pill mb-3">
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
          <span>Shared roast session</span>
          {session.is_ended && (
            <span className="ml-2 rounded-full border border-border/60 px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted">
              Ended
            </span>
          )}
        </span>
        <h1 className="font-display text-4xl font-extrabold gradient-text">
          {session.personality.replace("_", " ").toUpperCase()} · {session.mode.toUpperCase()}
        </h1>
        <p className="mt-2 text-muted">
          Session <span className="font-mono">{sessionId}</span> · {session.message_count} messages
        </p>
      </header>

      <div className="card mb-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Confidence Lost" value={`${session.scores.confidence_lost}%`} />
          <Stat label="Damage"          value={`${session.scores.emotional_damage}%`} />
          <Stat label="Reality Checks"  value={String(session.scores.reality_checks)} />
          <Stat label="Delusion"        value={session.scores.delusion_level} small />
        </div>
      </div>

      <div className="space-y-4">
        {session.history.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.04 }}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {m.role === "user" ? (
              <div className="user-bubble max-w-[80%] text-sm">{m.content}</div>
            ) : (
              <div className="roast-bubble max-w-[85%] text-[15px] leading-relaxed">
                {m.content}
              </div>
            )}
          </motion.div>
        ))}
      </div>

      <footer className="mt-10 text-center">
        <a href="/" className="btn-primary">Get roasted yourself 🔥</a>
      </footer>
    </article>
  );
}

function Stat({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`font-mono font-bold ${small ? "text-xs" : "text-2xl"} gradient-text`}>
        {value}
      </div>
    </div>
  );
}
