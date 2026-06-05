"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authApi, UserStats } from "../../lib/auth-api";

export default function StatsPage() {
  const [stats, setStats] = useState<UserStats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    authApi.myStats()
      .then(setStats)
      .catch((e) => setErr(e?.message || "Failed to load"));
  }, []);

  if (err) {
    return (
      <div className="mx-auto max-w-md card">
        <h1 className="font-display text-2xl font-bold gradient-text">Your stats</h1>
        <p className="mt-4 text-sm text-accent">{err}</p>
        <Link href="/login" className="btn-primary mt-3 inline-block">Log in</Link>
      </div>
    );
  }

  if (!stats) {
    return <p className="text-muted">Loading…</p>;
  }

  const personalityEntries = Object.entries(stats.score_by_personality);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="font-display text-3xl font-bold gradient-text">Your stats</h1>
        <p className="mt-1 text-sm text-muted">Everything we&apos;ve learned about how you take a roast.</p>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card label="Messages" value={stats.total_messages} />
        <Card label="Sessions" value={stats.total_sessions} />
        <Card label="Avg score" value={Math.round(stats.average_score * 10) / 10} />
        <Card label="Best" value={stats.best_score} />
        <Card label="Total score" value={stats.total_score} />
        <Card label="Achievements" value={`${stats.achievements_unlocked}/${stats.achievements_total}`} />
        <Card
          label="Rank"
          value={stats.rank ? `#${stats.rank}` : "—"}
          sub={stats.rank_period ?? undefined}
        />
        <Card label="Topics" value={stats.recent_topics.length} />
      </div>

      <section className="card">
        <h2 className="font-display text-lg font-semibold">Score by mode</h2>
        <BarList
          entries={Object.entries(stats.score_by_mode).map(([k, v]) => ({
            label: k,
            value: v.count,
            sub: `avg ${v.count ? Math.round(v.total / v.count) : 0}`,
          }))}
        />
      </section>

      {personalityEntries.length > 0 && (
        <section className="card">
          <h2 className="font-display text-lg font-semibold">Score by personality</h2>
          <BarList
            entries={personalityEntries.map(([k, v]) => ({
              label: k,
              value: v.count,
              sub: `avg ${v.count ? Math.round(v.total / v.count) : 0}`,
            }))}
          />
        </section>
      )}

      {stats.recent_topics.length > 0 && (
        <section className="card">
          <h2 className="font-display text-lg font-semibold">Recent topics</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {stats.recent_topics.map((t) => (
              <span key={t} className="rounded-full border border-border bg-surface px-3 py-1 text-xs">
                {t}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Card({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card text-center">
      <div className="font-display text-2xl font-bold gradient-text">{value}</div>
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      {sub && <div className="mt-1 text-[10px] text-muted">{sub}</div>}
    </div>
  );
}

function BarList({ entries }: { entries: { label: string; value: number; sub?: string }[] }) {
  if (entries.length === 0) {
    return <p className="mt-3 text-sm text-muted">No data yet — start a chat to fill this in.</p>;
  }
  const max = Math.max(1, ...entries.map((e) => e.value));
  return (
    <ul className="mt-3 space-y-2">
      {entries.map((e) => (
        <li key={e.label} className="text-sm">
          <div className="flex items-baseline justify-between">
            <span className="text-text">{e.label}</span>
            <span className="text-muted">
              {e.value}
              {e.sub && ` · ${e.sub}`}
            </span>
          </div>
          <div className="mt-1 h-2 w-full overflow-hidden rounded bg-border/40">
            <div
              className="h-full bg-gradient-to-r from-accent to-accent-2"
              style={{ width: `${(e.value / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
