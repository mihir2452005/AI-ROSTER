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
    return <main className="min-h-screen flex items-center justify-center text-slate-500">Loading…</main>;
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="max-w-3xl mx-auto">
        <header className="mb-6 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Your history</h1>
            <p className="text-sm text-slate-500">{total} message{total === 1 ? "" : "s"} saved</p>
          </div>
          <div className="flex gap-2">
            <a href="/account" className="text-sm text-purple-600 hover:underline">← Account</a>
            {items.length > 0 && (
              <button
                onClick={clearAll}
                className="text-sm text-red-600 hover:underline"
              >
                Clear all
              </button>
            )}
          </div>
        </header>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-800 text-sm">
            {error}
          </div>
        )}

        {items.length === 0 ? (
          <div className="bg-white rounded-xl p-8 text-center text-slate-500">
            <p>No history yet. Start a session to fill this page.</p>
            <a
              href="/"
              className="mt-4 inline-block px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg"
            >
              Start a session
            </a>
          </div>
        ) : (
          days.map((day) => (
            <section key={day} className="mb-6">
              <h2 className="text-xs uppercase font-semibold text-slate-500 mb-2">{day}</h2>
              <div className="bg-white rounded-xl shadow-sm divide-y">
                {grouped[day].map((it) => (
                  <div
                    key={it.id}
                    className={`px-4 py-3 ${it.is_user ? "bg-slate-50" : ""}`}
                  >
                    <div className="text-xs text-slate-400 mb-1">
                      {it.is_user ? "👤 You" : "🤖 RoastGPT"}
                      {it.score_total > 0 && (
                        <span className="ml-2 text-red-500">−{it.score_total} HP</span>
                      )}
                    </div>
                    <div className="text-sm text-slate-800 whitespace-pre-wrap">
                      {it.message}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </main>
  );
}
