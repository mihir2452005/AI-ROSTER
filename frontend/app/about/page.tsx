export default function AboutPage() {
  return (
    <article className="prose prose-invert mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold">About RoastGPT</h1>
      <p className="text-muted">
        RoastGPT is a multi-mode roast-combat engine built on top of the latest large
        language models, with a free tier for casual users and paid plans for power
        roasters. It is a solo project maintained by{" "}
        <a className="text-accent-3" href="https://github.com/mihir2452005" rel="noreferrer">
          Mihir Kadam
        </a>{" "}
        and a small group of contributors.
      </p>

      <h2 className="mt-8 font-display text-2xl">What we believe</h2>
      <ul className="text-muted">
        <li><strong>AI should be fun.</strong> Not just productivity. Roasts, jokes, banter, and bad puns are a legitimate use of compute.</li>
        <li><strong>Privacy is the default.</strong> No training on your chats. No ads. No third-party trackers.</li>
        <li><strong>Free tiers should be real.</strong> You can have a meaningful experience without ever paying us.</li>
        <li><strong>The product should be small enough to hold in your head.</strong> One screen, one input, one button. The complexity lives in the backend.</li>
      </ul>

      <h2 className="mt-8 font-display text-2xl">How it&apos;s built</h2>
      <p className="text-muted">
        The backend is FastAPI on Python 3.12, talking to Postgres (Neon), Redis (Upstash),
        and a Celery-style RQ worker for background jobs. The frontend is Next.js 14 on
        the App Router. Sentry catches errors. We deploy on Render and Vercel — both free
        tiers, both zero-downtime.
      </p>
      <p className="text-muted">
        Every line is open source. The full history, the bug tracker, the design docs, and
        the public roadmap live on{" "}
        <a className="text-accent-3" href="https://github.com/mihir2452005/AI-ROSTER" rel="noreferrer">
          GitHub
        </a>.
      </p>

      <h2 className="mt-8 font-display text-2xl">Contact</h2>
      <p className="text-muted">
        General questions: <a className="text-accent-3" href="mailto:support@roastgpt.app">support@roastgpt.app</a><br />
        Security issues: <a className="text-accent-3" href="mailto:security@roastgpt.app">security@roastgpt.app</a><br />
        Or open a ticket on the <a className="text-accent-3" href="/contact">contact page</a>.
      </p>
    </article>
  );
}
