"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

interface Entry {
  rank: number;
  user_id: number;
  display_name: string;
  masked_email: string | null;
  total_damage: number;
  message_count: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchLeaderboard(period: string, limit = 10): Promise<{ period: string; entries: Entry[] }> {
  const res = await fetch(`${API_BASE}/api/leaderboard?period=${period}&limit=${limit}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to load leaderboard");
  return res.json();
}

const TABS = [
  { key: "week",  label: "This week" },
  { key: "month", label: "This month" },
  { key: "all",   label: "All time" },
] as const;

type Period = typeof TABS[number]["key"];

export default function LeaderboardPage() {
  const [period, setPeriod] = useState<Period>("week");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchLeaderboard(period)
      .then((d) => setEntries(d.entries))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [period]);

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6 text-center">
        <h1 className="font-display text-5xl font-extrabold gradient-text">
          The Burn Board 🔥
        </h1>
        <p className="mt-3 text-muted">
          Top damage leaders. Roast hard, climb high.
        </p>
      </header>

      <div className="mb-4 flex justify-center gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setPeriod(t.key)}
            className={`px-3 py-1.5 text-sm rounded ${
              period === t.key ? "bg-accent text-white" : "bg-surface/50 text-muted hover:text-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card">
        {loading && <p className="p-6 text-center text-muted">Loading…</p>}
        {error && <p className="p-6 text-center text-red-500">{error}</p>}
        {!loading && !error && entries.length === 0 && (
          <p className="p-6 text-center text-muted">
            No activity in this period yet. Be the first to climb the board.
          </p>
        )}
        {!loading && !error && entries.length > 0 && (
          <div className="space-y-2">
            {entries.map((row) => (
              <motion.div
                key={row.user_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: row.rank * 0.04 }}
                className="flex items-center gap-4 rounded-lg border border-border/60 bg-bg/40 p-3"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface font-mono font-bold text-base">
                  {row.rank <= 3 ? ["🥇", "🥈", "🥉"][row.rank - 1] : `#${row.rank}`}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold">{row.display_name}</div>
                  <div className="text-xs text-muted">
                    {row.message_count} message{row.message_count === 1 ? "" : "s"} ·{" "}
                    {row.masked_email || "—"}
                  </div>
                </div>
                <div className="font-mono text-lg font-bold gradient-text">
                  {row.total_damage.toFixed(0)}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-6 text-center text-xs text-muted">
        Want your name on the board?{" "}
        <a href="/" className="text-accent-3 hover:underline">Get roasted</a>.
        {" "}Top scorers get featured rewards 🎁
      </div>
    </div>
  );
}
