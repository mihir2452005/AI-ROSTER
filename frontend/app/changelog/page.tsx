import Link from "next/link";

type Entry = {
  version: string;
  date: string;
  highlights: string[];
  fixes?: string[];
};

const ENTRIES: Entry[] = [
  {
    version: "1.4.0",
    date: "2026-06-06",
    highlights: [
      "Public contact form at /contact (XSS-stripped before storage).",
      "Admin inbox at /admin → Contact Messages tab.",
      "In-app notification center — bell icon in the header with unread badge.",
      "Account → Recent Activity feed powered by the audit log.",
      "Public status page at /status with DB / cache / queue / Sentry health.",
      "Prometheus /api/v1/system/metrics endpoint with 14 gauges.",
      "Maintenance mode flag — when on, non-admin requests get a 503.",
      "Four new email templates: welcome, payment success, expiring soon, cancelled.",
      "Welcome notification + welcome email on register.",
      "Password-change + payment + cancellation notifications + emails.",
      "New /faq and /changelog pages.",
    ],
    fixes: [
      "Old /api/metrics endpoint now delegates to the comprehensive Prometheus output.",
      "Maintenance middleware skip list updated to include unversioned /api/system/* paths.",
    ],
  },
  {
    version: "1.3.0",
    date: "2026-05-20",
    highlights: [
      "Role-based access control (Role.user / Role.admin / Role.moderator).",
      "Redis cache backend (Upstash) with in-memory fallback for dev.",
      "Celery-style background task queue with RQ fallback.",
      "Sentry error tracking (free tier).",
      "Continue previous chat — 'Resume' button on history sessions.",
      "Public share links with one-click revoke and a 30-day expiry default.",
    ],
  },
  {
    version: "1.2.0",
    date: "2026-05-04",
    highlights: [
      "Upgrade / downgrade plan from the Account page.",
      "Daily leaderboard snapshot job (replaces live-count fallback).",
      "Public /api/metrics endpoint with process-level gauges.",
      "Admin tabs: Signups Chart, Chat Volume Chart, Audit Log, User Achievements.",
    ],
  },
  {
    version: "1.1.0",
    date: "2026-04-18",
    highlights: [
      "Achievements system with 12 unlockable badges.",
      "History search, export (txt / md / json).",
      "User memory table: per-mode counts, recent topics, score.",
      "Ban / unban + admin audit log.",
    ],
  },
  {
    version: "1.0.0",
    date: "2026-04-01",
    highlights: [
      "Initial public release.",
      "Four roast modes (Friend, Savage, Flirty, Motivational) across five personalities.",
      "Free tier (5 messages) + Pro / Premium subscription tiers.",
      "Razorpay payments, history, share, leaderboard, achievements.",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <article className="prose prose-invert mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold">Changelog</h1>
      <p className="text-muted">
        New features, fixes, and breaking changes. Subscribe to releases on{" "}
        <a className="text-accent-3" href="https://github.com/mihir2452005/AI-ROSTER/releases" rel="noreferrer">
          GitHub
        </a>{" "}
        to get an email when a new version ships.
      </p>

      <ol className="relative mt-8 space-y-10 border-l border-white/10 pl-6">
        {ENTRIES.map((entry) => (
          <li key={entry.version} className="relative">
            <span
              aria-hidden
              className="absolute -left-[33px] mt-1.5 h-3 w-3 rounded-full border-2 border-bg bg-accent-3"
            />
            <h2 className="font-display text-2xl">
              v{entry.version}{" "}
              <span className="text-sm font-normal text-muted">— {entry.date}</span>
            </h2>
            <h3 className="mt-3 text-sm font-semibold uppercase tracking-wide text-accent-3">Highlights</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-fg">
              {entry.highlights.map((h) => <li key={h}>{h}</li>)}
            </ul>
            {entry.fixes && entry.fixes.length > 0 && (
              <>
                <h3 className="mt-3 text-sm font-semibold uppercase tracking-wide text-accent-3">Fixes</h3>
                <ul className="mt-1 list-disc pl-5 text-sm text-fg">
                  {entry.fixes.map((f) => <li key={f}>{f}</li>)}
                </ul>
              </>
            )}
          </li>
        ))}
      </ol>

      <p className="mt-10 text-sm text-muted">
        Looking for the older history? It&apos;s on{" "}
        <a className="text-accent-3" href="https://github.com/mihir2452005/AI-ROSTER/releases">GitHub Releases</a>.
      </p>
    </article>
  );
}
