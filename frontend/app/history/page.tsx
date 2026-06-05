"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { historyApi, getAccessToken, type ChatHistoryItem } from "../../lib/auth-api";

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<ChatHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [pendingQ, setPendingQ] = useState("");
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced search — wait 300ms after typing stops so we don't fire
  // a request per keystroke.
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setQ(pendingQ.trim());
    }, 300);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [pendingQ]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    setLoading(true);
    historyApi
      .list({ limit: 200, q: q || undefined })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => {
        if (e?.status === 401) router.push("/login");
        else setError(e?.detail || "Failed to load");
      })
      .finally(() => setLoading(false));
  }, [router, q]);

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

  async function downloadExport(format: "txt" | "md" | "json") {
    try {
      const res = await historyApi.export(format);
      if (!res.ok) {
        toast.error("Export failed");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `roastgpt-history.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoke after a short delay so the click handler completes
      // first on slow browsers.
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      toast.success("Exported");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Export failed";
      toast.error(msg);
    }
  }

  async function copyAll() {
    if (items.length === 0) {
      toast.error("Nothing to copy");
      return;
    }
    const lines = items.map((it) => {
      const who = it.is_user ? "You" : "RoastGPT";
      const score = it.score_total > 0 ? `  [−${it.score_total} HP]` : "";
      return `${who}: ${it.message}${score}`;
    });
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      toast.success(`Copied ${items.length} messages`);
    } catch {
      toast.error("Could not copy");
    }
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
          <div className="text-4xl animate-pulse">🔥</div>
          <p className="mt-3 text-sm">Loading history…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6 flex items-center justify-between gap-2">
        <div>
          <h1 className="font-display text-3xl font-bold">Your history</h1>
          <p className="text-sm text-muted">
            {q ? `${total} match${total === 1 ? "" : "es"} for "${q}"` : `${total} message${total === 1 ? "" : "s"} saved`}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <a href="/account" className="text-sm text-accent-3 hover:underline">← Account</a>
        </div>
      </header>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          type="search"
          value={pendingQ}
          onChange={(e) => setPendingQ(e.target.value)}
          placeholder="Search messages…"
          className="input flex-1"
          aria-label="Search history"
        />
        <div className="flex flex-wrap gap-2">
          <button onClick={copyAll} className="btn-ghost text-xs" disabled={items.length === 0}>
            Copy
          </button>
          <button onClick={() => downloadExport("txt")} className="btn-ghost text-xs" disabled={items.length === 0}>
            Export .txt
          </button>
          <button onClick={() => downloadExport("md")} className="btn-ghost text-xs" disabled={items.length === 0}>
            Export .md
          </button>
          <button onClick={() => downloadExport("json")} className="btn-ghost text-xs" disabled={items.length === 0}>
            Export .json
          </button>
        </div>
      </div>

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
          {q ? (
            <>
              <p>No history matches &quot;{q}&quot;.</p>
              <button onClick={() => { setPendingQ(""); setQ(""); }} className="btn-ghost mt-3 text-sm">
                Clear search
              </button>
            </>
          ) : (
            <>
              <p>No history yet. Start a session to fill this page.</p>
              <a href="/" className="btn-primary mt-4 text-sm">
                Start a session
              </a>
            </>
          )}
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
                    {it.is_user ? "👤 You" : "🤖 RoastGPT"}
                    {it.score_total > 0 && (
                      <span className="ml-2 text-accent">−{it.score_total} HP</span>
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

      {items.length > 0 && (
        <div className="mt-6 text-right">
          <button
            onClick={clearAll}
            className="text-sm text-accent hover:underline"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
