"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { notificationsApi, type Notification } from "@/lib/auth-api";

const POLL_MS = 60_000;

export function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const res = await notificationsApi.list({ limit: 10 });
      setItems(res.items);
      setUnread(res.unread_count);
    } catch {
      // Silent — bell degrades gracefully if the endpoint is down.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  // Click-outside to close.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  async function onClickItem(n: Notification) {
    if (!n.is_read) {
      try {
        await notificationsApi.markRead([n.id]);
        setItems((prev) => prev.map((x) => x.id === n.id ? { ...x, is_read: true } : x));
        setUnread((u) => Math.max(0, u - 1));
      } catch {
        // ignore
      }
    }
    setOpen(false);
    if (n.link) router.push(n.link);
  }

  async function onMarkAll() {
    try {
      const res = await notificationsApi.markAllRead();
      setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
      setUnread(0);
      if (res.updated) {
        // No-op; the state already reflects the change.
      }
    } catch {
      // ignore
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ""}`}
        onClick={() => setOpen((o) => !o)}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-surface/60 text-fg transition hover:border-accent-3/40"
      >
        <span aria-hidden>🔔</span>
        {unread > 0 && (
          <span
            className="absolute -right-1 -top-1 min-w-[1.1rem] rounded-full bg-rose-500 px-1 text-center text-[10px] font-bold text-white"
            aria-hidden
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="absolute right-0 z-50 mt-2 w-80 max-w-[90vw] overflow-hidden rounded-md border border-white/10 bg-surface shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                onClick={onMarkAll}
                className="text-xs text-accent-3 hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading && items.length === 0 && (
              <div className="px-3 py-4 text-sm text-muted">Loading…</div>
            )}
            {!loading && items.length === 0 && (
              <div className="px-3 py-6 text-center text-sm text-muted">
                You&apos;re all caught up.
              </div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => onClickItem(n)}
                className={`flex w-full items-start gap-2 border-b border-white/5 px-3 py-2 text-left text-sm transition hover:bg-white/5 ${
                  n.is_read ? "text-muted" : "text-fg"
                }`}
              >
                <span
                  aria-hidden
                  className={`mt-1 h-2 w-2 flex-shrink-0 rounded-full ${n.is_read ? "bg-white/20" : "bg-accent-3"}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{n.title}</div>
                  <div className="line-clamp-2 text-xs text-muted">{n.body}</div>
                  <div className="mt-0.5 text-[10px] uppercase tracking-wide text-muted/70">
                    {n.kind} · {new Date(n.created_at).toLocaleString()}
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="border-t border-white/10 px-3 py-2 text-center">
            <Link
              href="/account"
              className="text-xs text-accent-3 hover:underline"
              onClick={() => setOpen(false)}
            >
              See full activity on Account
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
