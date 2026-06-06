"use client";

import { useEffect, useState } from "react";
import { systemApi, type SystemStatus } from "@/lib/auth-api";

const POLL_MS = 30_000;

const STATE_TONE: Record<string, string> = {
  // status
  healthy: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  degraded: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  unhealthy: "bg-rose-500/15 text-rose-200 border-rose-500/30",
  // database
  ok: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  // cache
  redis: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  memory: "bg-sky-500/15 text-sky-200 border-sky-500/30",
  down: "bg-rose-500/15 text-rose-200 border-rose-500/30",
  // queue
  active: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  inactive: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  disabled: "bg-white/10 text-muted border-white/20",
  // sentry
  // (covered by active/inactive/disabled above)
};

function Tone({ value }: { value: string }) {
  const cls = STATE_TONE[value] || STATE_TONE.disabled;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${cls}`}>
      {value}
    </span>
  );
}

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

export default function StatusPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<number>(0);

  async function fetchStatus(silent = false) {
    if (!silent) setError(null);
    try {
      const s = await systemApi.status();
      setStatus(s);
      setLastFetched(Date.now());
    } catch (e: any) {
      setError(e?.message || "Unable to reach the status endpoint");
    }
  }

  useEffect(() => {
    fetchStatus();
    const id = window.setInterval(() => fetchStatus(true), POLL_MS);
    return () => window.clearInterval(id);
  }, []);

  return (
    <article className="prose prose-invert mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold">System status</h1>
      <p className="text-muted">
        Live health of the RoastGPT service. This page polls the public status endpoint
        every 30 seconds — no auth required.
      </p>

      {error && (
        <div role="alert" className="mt-4 rounded-md border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      )}

      {status && (
        <>
          {status.maintenance_mode && (
            <div role="alert" className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              <strong>Maintenance window in progress.</strong> The service is intentionally
              returning 503 to non-admin users. Admins can still use the API.
            </div>
          )}

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <Card label="Overall" value={<Tone value={status.status} />} />
            <Card label="Database" value={<Tone value={status.database} />} />
            <Card label="Cache" value={<Tone value={status.redis} />} />
            <Card label="Background queue" value={<Tone value={status.queue} />} />
            <Card label="Error tracking" value={<Tone value={status.sentry} />} />
            <Card label="Maintenance mode" value={<Tone value={status.maintenance_mode ? "active" : "disabled"} />} />
          </div>

          <h2 className="mt-8 font-display text-2xl">Build</h2>
          <ul className="text-muted">
            <li>Version: <code className="rounded bg-white/5 px-1 text-xs">v{status.version}</code></li>
            <li>Build SHA: <code className="rounded bg-white/5 px-1 text-xs">{status.build_sha || "unknown"}</code></li>
            <li>Uptime: {Math.floor(status.uptime_seconds / 60)} minutes</li>
            <li>Last refreshed: {lastFetched ? timeAgo(new Date(lastFetched).toISOString()) : "—"}</li>
          </ul>

          <h2 className="mt-8 font-display text-2xl">Recent incidents</h2>
          <p className="text-muted">
            No incidents in the last 30 days. Subscribe to{" "}
            <a className="text-accent-3" href="https://github.com/mihir2452005/AI-ROSTER/releases">release notifications</a>
            {" "}or check the <a className="text-accent-3" href="/changelog">changelog</a> for the
            full history.
          </p>
        </>
      )}
    </article>
  );
}

function Card({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-white/10 bg-surface/40 p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-2">{value}</div>
    </div>
  );
}
