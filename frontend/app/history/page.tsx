"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { historyApi, getAccessToken, type ChatHistoryItem } from "../../lib/auth-api";

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<ChatHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    historyApi
      .list({ limit: 100 })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => {
        if (e?.status === 401) router.push("/login");
        else setError(e?.detail || "Failed to load");
      })
      .finally(() => setLoading(false));
  }, [router]);

  function clearAll() {
    if (!confirm("Delete all your chat history? This cannot be undone.")) return;
    setError("");
    historyApi
      .clear()
      .then((r) => {
        setItems([]);
        setTotal(0);
        setError(r.message);
      })
      .catch((e) => setError("Clear failed: " + (e?.detail || "")));
  }

  // Group by date for readability
  const grouped: Record<string, ChatHistoryItem[]> = {};
  for (const it of items) {
    const day = new Date(it.created_at).toLocaleDateString();
    if (!grouped[day]) grouped[day] = [];
    grouped[day].push(it);
  }
  const days = Object.keys(grouped);

  if (loading) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-muted">
        <div className="text-center">
          <div className="text-4xl animate-pulse">ðŸ”¥</div>
          <p className="mt-3 text-sm">Loading historyâ€¦</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold">Your history</h1>
          <p className="text-sm text-muted">{total} message{total === 1 ? "" : "s"} saved</p>
        </div>
        <div className="flex gap-2">
          <a href="/account" className="text-sm text-accent-3 hover:underline">â† Account</a>
          {items.length > 0 && (
            <button
              onClick={clearAll}
              className="text-sm text-accent hover:underline"
            >
              Clear all
            </button>
          )}
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-accent/40 bg-accent/10 p-3 text-sm text-accent"
        >
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="card p-8 text-center text-muted">
          <p>No history yet. Start a session to fill this page.</p>
          <a href="/" className="btn-primary mt-4 text-sm">
            Start a session
          </a>
        </div>
      ) : (
        days.map((day) => (
          <section key={day} className="mb-6">
            <h2 className="mb-2 text-xs font-semibold uppercase text-muted">{day}</h2>
            <div className="card divide-y divide-border/60 p-0">
              {grouped[day].map((it) => (
                <div
                  key={it.id}
                  className={`px-4 py-3 ${it.is_user ? "bg-surface/30" : ""}`}
                >
                  <div className="mb-1 text-xs text-muted">
                    {it.is_user ? "ðŸ‘¤ You" : "ðŸ¤– RoastGPT"}
                    {it.score_total > 0 && (
                      <span className="ml-2 text-accent">âˆ’{it.score_total} HP</span>
                    )}
                  </div>
                  <div className="whitespace-pre-wrap text-sm">
                    {it.message}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
