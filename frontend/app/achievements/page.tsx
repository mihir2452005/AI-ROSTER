"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { authApi, UserStats } from "../../lib/auth-api";

export default function AchievementsPage() {
  const [stats, setStats] = useState<UserStats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    authApi.me()
      .then(() => authApi.myStats())
      .then((s) => {
        if (mounted) {
          setStats(s);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (mounted) {
          setErr(e?.message || "Failed to load");
          setLoading(false);
        }
      });
    return () => { mounted = false; };
  }, []);

  const onCopy = async () => {
    if (!stats) return;
    const lines = [
      "🏆 RoastGPT Achievements",
      `Unlocked: ${stats.achievements_unlocked} / ${stats.achievements_total}`,
      `Total messages: ${stats.total_messages}`,
      `Best score: ${stats.best_score}`,
      `Average score: ${Math.round(stats.average_score * 10) / 10}`,
      stats.rank ? `Rank: #${stats.rank} (${stats.rank_period})` : "Rank: unranked",
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="flex items-center justify-between gap-2">
        <h1 className="font-display text-3xl font-bold gradient-text">Achievements</h1>
        {stats && stats.total_messages > 0 && (
          <button className="btn-ghost text-sm" onClick={onCopy}>Copy summary</button>
        )}
      </header>

      {loading && <p className="text-muted">Loading…</p>}

      {err && (
        <div className="card border-accent/40">
          <p className="text-sm text-accent">{err}</p>
          <p className="mt-2 text-sm text-muted">
            You need to be signed in.
          </p>
          <Link href="/login" className="btn-primary mt-3 inline-block">Log in</Link>
        </div>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Unlocked" value={`${stats.achievements_unlocked}/${stats.achievements_total}`} />
            <Stat label="Messages" value={stats.total_messages} />
            <Stat label="Best score" value={stats.best_score} />
            <Stat label="Rank" value={stats.rank ? `#${stats.rank}` : "—"} sub={stats.rank_period ?? undefined} />
          </div>

          <section className="card">
            <h2 className="font-display text-lg font-semibold">Score by mode</h2>
            <ul className="mt-3 space-y-1 text-sm">
              {Object.entries(stats.score_by_mode).length === 0 && (
                <li className="text-muted">No data yet — start a chat to earn stats.</li>
              )}
              {Object.entries(stats.score_by_mode).map(([mode, v]) => (
                <li key={mode} className="flex items-center justify-between">
                  <span className="text-text">{mode}</span>
                  <span className="text-muted">
                    {v.count} chats · avg {v.count ? Math.round(v.total / v.count) : 0}
                  </span>
                </li>
              ))}
            </ul>
          </section>

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

          <p className="text-xs text-muted">
            Achievements unlock automatically as you chat. See <Link href="/stats" className="text-accent-2 hover:underline">stats</Link> for full breakdowns.
          </p>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card text-center">
      <div className="font-display text-2xl font-bold gradient-text">{value}</div>
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      {sub && <div className="mt-1 text-[10px] text-muted">{sub}</div>}
    </div>
  );
}
