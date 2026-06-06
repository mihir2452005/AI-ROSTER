"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "roastgpt:cookie-acknowledged";

export function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      const ack = localStorage.getItem(STORAGE_KEY);
      if (!ack) setVisible(true);
    } catch {
      // localStorage blocked; hide the banner rather than nag.
      setVisible(false);
    }
  }, []);

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, new Date().toISOString());
    } catch {
      // ignore
    }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Cookie notice"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-surface/95 px-4 py-3 shadow-lg backdrop-blur-md"
    >
      <div className="mx-auto flex max-w-5xl flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          We use a single first-party cookie to keep you signed in and remember your
          theme. No third-party trackers, no ads. See the{" "}
          <a className="text-accent-3 hover:underline" href="/privacy">privacy policy</a>
          {" "}for the full list.
        </p>
        <div className="flex gap-2">
          <a
            href="/privacy"
            className="rounded-md border border-white/10 px-3 py-1.5 text-xs text-muted hover:border-accent-3/40"
          >
            Learn more
          </a>
          <button
            type="button"
            onClick={dismiss}
            className="rounded-md bg-accent-3 px-3 py-1.5 text-xs font-semibold text-black transition hover:brightness-110"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
