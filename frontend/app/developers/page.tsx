type Endpoint = {
  method: string;
  path: string;
  description: string;
  auth?: string;
};

type Group = {
  name: string;
  base: string;
  endpoints: Endpoint[];
};

const GROUPS: Group[] = [
  {
    name: "Auth",
    base: "/api/v1/auth",
    endpoints: [
      { method: "POST", path: "/register", description: "Create a new account, return access + refresh tokens." },
      { method: "POST", path: "/login", description: "Email + password → tokens." },
      { method: "POST", path: "/refresh", description: "Refresh access token from a valid refresh." },
      { method: "POST", path: "/logout", description: "Revoke the current access token.", auth: "user" },
      { method: "POST", path: "/logout-all", description: "Revoke every token (bumps token_version).", auth: "user" },
      { method: "POST", path: "/change-password", description: "Change password; bumps token_version.", auth: "user" },
      { method: "POST", path: "/forgot-password", description: "Send a password-reset email (always 200 to avoid email-enumeration)." },
      { method: "POST", path: "/reset-password", description: "Consume the reset token, set a new password." },
      { method: "POST", path: "/send-verification", description: "Send a verification email.", auth: "user" },
      { method: "POST", path: "/verify-email", description: "Consume a verification token, mark the user verified." },
      { method: "GET", path: "/me", description: "Current user profile.", auth: "user" },
      { method: "PATCH", path: "/me", description: "Update full_name, gender_preference, favorite_mode.", auth: "user" },
      { method: "POST", path: "/me/avatar", description: "Set avatar (data URI or HTTPS URL).", auth: "user" },
      { method: "DELETE", path: "/me", description: "Soft-delete the account (30-day purge).", auth: "user" },
      { method: "GET", path: "/me/activity", description: "Recent Activity feed from the audit log.", auth: "user" },
    ],
  },
  {
    name: "Chat sessions",
    base: "/api/v1/chat",
    endpoints: [
      { method: "POST", path: "/session/start", description: "Start a new roast session.", auth: "user" },
      { method: "POST", path: "/session/{id}/roast", description: "Send a message, get the next roast.", auth: "user" },
      { method: "POST", path: "/session/{id}/end", description: "End the session (computes final score).", auth: "user" },
      { method: "POST", path: "/session/{id}/recover", description: "Recover a previous session's state.", auth: "user" },
      { method: "POST", path: "/session/{id}/share", description: "Create a public share link.", auth: "user" },
    ],
  },
  {
    name: "History",
    base: "/api/v1/history",
    endpoints: [
      { method: "GET", path: "/", description: "List past messages, paginated. Supports ?q= for search.", auth: "user" },
      { method: "DELETE", path: "/", description: "Bulk delete history.", auth: "user" },
      { method: "GET", path: "/export?format=txt|md|json", description: "Download the full history.", auth: "user" },
    ],
  },
  {
    name: "Payments",
    base: "/api/v1/payments",
    endpoints: [
      { method: "GET", path: "/plans", description: "Public list of available plans." },
      { method: "POST", path: "/create-order", description: "Create a Razorpay order for a plan.", auth: "user" },
      { method: "POST", path: "/verify", description: "Verify a captured payment and activate the subscription.", auth: "user" },
      { method: "POST", path: "/webhook", description: "Razorpay webhook handler (signature-verified)." },
      { method: "GET", path: "/history", description: "User's payment history.", auth: "user" },
    ],
  },
  {
    name: "Subscriptions",
    base: "/api/v1/subscriptions",
    endpoints: [
      { method: "GET", path: "/current", description: "The current subscription, if any.", auth: "user" },
      { method: "POST", path: "/cancel", description: "Schedule cancellation at period end.", auth: "user" },
      { method: "POST", path: "/upgrade", description: "Upgrade to a higher plan (prorated).", auth: "user" },
      { method: "POST", path: "/downgrade", description: "Downgrade at the end of the current period.", auth: "user" },
    ],
  },
  {
    name: "Leaderboard",
    base: "/api/v1/leaderboard",
    endpoints: [
      { method: "GET", path: "/?period=week|month", description: "Top-N public leaderboard." },
    ],
  },
  {
    name: "Admin",
    base: "/api/v1/admin",
    endpoints: [
      { method: "GET", path: "/stats", description: "Aggregate stats (users, subs, payments).", auth: "admin" },
      { method: "GET", path: "/users", description: "List users with search + pagination.", auth: "admin" },
      { method: "GET", path: "/users/{id}", description: "Single user detail.", auth: "admin" },
      { method: "POST", path: "/users/{id}/ban", description: "Ban a user.", auth: "admin" },
      { method: "POST", path: "/users/{id}/unban", description: "Unban a user.", auth: "admin" },
      { method: "POST", path: "/grant-subscription", description: "Manually grant a paid plan.", auth: "admin" },
      { method: "GET", path: "/feature-flags", description: "Read all flags.", auth: "admin" },
      { method: "PATCH", path: "/feature-flags", description: "Toggle a flag.", auth: "admin" },
      { method: "GET", path: "/audit-logs", description: "Append-only audit log.", auth: "admin" },
      { method: "GET", path: "/contact-messages", description: "Inbox of contact-form submissions.", auth: "admin" },
      { method: "PATCH", path: "/contact-messages/{id}?status=", description: "Mark a contact message handled/spam.", auth: "admin" },
      { method: "POST", path: "/notifications/broadcast", description: "Push a notification to all or one user.", auth: "admin" },
      { method: "GET", path: "/charts/signups?days=30", description: "Daily signup counts.", auth: "admin" },
      { method: "GET", path: "/charts/chats?days=30", description: "Daily chat-message counts.", auth: "admin" },
    ],
  },
  {
    name: "Notifications & contact (user)",
    base: "/api/v1",
    endpoints: [
      { method: "GET", path: "/notifications", description: "List the current user's notifications.", auth: "user" },
      { method: "POST", path: "/notifications/mark-read", description: "Mark specific notification ids read (scoped to caller).", auth: "user" },
      { method: "POST", path: "/notifications/mark-all-read", description: "Mark every notification read.", auth: "user" },
      { method: "POST", path: "/contact", description: "Submit a contact-form message (no auth)." },
    ],
  },
  {
    name: "System (public)",
    base: "/api/v1/system",
    endpoints: [
      { method: "GET", path: "/status", description: "Public health snapshot (db, cache, queue, sentry, version, maintenance flag)." },
      { method: "GET", path: "/metrics", description: "Prometheus text exposition (text/plain; version=0.0.4)." },
    ],
  },
];

const methodColor: Record<string, string> = {
  GET: "bg-emerald-500/20 text-emerald-200",
  POST: "bg-sky-500/20 text-sky-200",
  PATCH: "bg-amber-500/20 text-amber-200",
  DELETE: "bg-rose-500/20 text-rose-200",
};

export default function DevelopersPage() {
  return (
    <article className="prose prose-invert mx-auto max-w-5xl">
      <h1 className="font-display text-4xl font-bold">Developers</h1>
      <p className="text-muted">
        The complete surface of the RoastGPT HTTP API. Every endpoint is exposed at
        <code className="mx-1 rounded bg-white/5 px-1 text-xs">/api/v1/*</code>
        and (for backward compatibility) at the unversioned
        <code className="mx-1 rounded bg-white/5 px-1 text-xs">/api/*</code> alias. All
        requests and responses are JSON unless otherwise noted. Auth uses bearer tokens in
        the <code className="mx-1 rounded bg-white/5 px-1 text-xs">Authorization</code> header.
      </p>

      <h2 className="mt-8 font-display text-2xl">Quick start</h2>
      <pre className="overflow-x-auto rounded-md border border-white/10 bg-surface p-3 text-xs"><code>{`# 1. Register
curl -X POST https://api.roastgpt.app/api/v1/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{"email":"me@example.com","password":"hunter2hunter2"}'

# 2. Use the access token
curl https://api.roastgpt.app/api/v1/auth/me \\
  -H "Authorization: Bearer <token>"

# 3. Start a session, send a roast
curl -X POST https://api.roastgpt.app/api/v1/chat/session/start \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{"mode":"savage","personality":"sarcastic"}'`}</code></pre>

      <h2 className="mt-8 font-display text-2xl">Rate limits</h2>
      <p className="text-muted">
        Every endpoint is rate-limited per IP and per user where applicable. The defaults
        (overrideable in your own deployment) are:
      </p>
      <ul className="text-muted">
        <li>120 requests / minute per IP for read-only endpoints.</li>
        <li>20 requests / hour per IP for <code>POST /api/v1/auth/register</code>.</li>
        <li>30 requests / hour per IP for <code>POST /api/v1/auth/login</code>.</li>
        <li>10 requests / hour per IP for <code>POST /api/v1/contact</code>.</li>
      </ul>
      <p className="text-muted">
        The standard <code>X-RateLimit-Limit</code>, <code>X-RateLimit-Remaining</code>, and
        <code>X-RateLimit-Reset</code> headers are sent on every response. Exceeding a limit
        returns 429 with a <code>Retry-After</code> header.
      </p>

      <h2 className="mt-8 font-display text-2xl">Endpoints</h2>
      <div className="mt-4 space-y-8">
        {GROUPS.map((group) => (
          <section key={group.name}>
            <h3 className="font-display text-lg">
              {group.name}{" "}
              <span className="text-xs font-mono text-muted">{group.base}</span>
            </h3>
            <div className="mt-2 overflow-x-auto rounded-md border border-white/10">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/5 text-muted">
                  <tr>
                    <th className="w-20 px-3 py-2">Method</th>
                    <th className="px-3 py-2">Path</th>
                    <th className="px-3 py-2">Description</th>
                    <th className="w-16 px-3 py-2">Auth</th>
                  </tr>
                </thead>
                <tbody>
                  {group.endpoints.map((e, i) => (
                    <tr key={i} className="border-t border-white/5">
                      <td className="px-3 py-2 align-top">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${methodColor[e.method] || "bg-white/10"}`}>
                          {e.method}
                        </span>
                      </td>
                      <td className="px-3 py-2 align-top font-mono text-fg">
                        {e.path}
                      </td>
                      <td className="px-3 py-2 align-top text-muted">
                        {e.description}
                      </td>
                      <td className="px-3 py-2 align-top text-[10px] text-muted">
                        {e.auth || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>

      <h2 className="mt-8 font-display text-2xl">Webhooks</h2>
      <p className="text-muted">
        The only public webhook today is Razorpay&apos;s payment-capture callback at
        <code className="mx-1 rounded bg-white/5 px-1 text-xs">POST /api/v1/payments/webhook</code>.
        Every request is verified against the <code>X-Razorpay-Signature</code> header using
        HMAC-SHA256 with your Razorpay webhook secret. Invalid signatures are rejected with
        a 401 and logged to Sentry.
      </p>

      <h2 className="mt-8 font-display text-2xl">OpenAPI / Swagger</h2>
      <p className="text-muted">
        The interactive OpenAPI 3.1 spec is served from the running backend at
        <code className="mx-1 rounded bg-white/5 px-1 text-xs">/docs</code> and the raw JSON
        at <code className="mx-1 rounded bg-white/5 px-1 text-xs">/openapi.json</code>.
        In production the docs are gated behind admin auth.
      </p>
    </article>
  );
}
