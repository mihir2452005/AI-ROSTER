export default function PrivacyPage() {
  return (
    <article className="prose prose-invert mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold">Privacy Policy</h1>
      <p className="text-sm text-muted">Last updated: 2026.</p>

      <h2 className="mt-6 font-display text-2xl">What we collect</h2>
      <ul className="list-disc pl-6 text-muted">
        <li><strong>Account data</strong>: email, display name, gender preference.</li>
        <li><strong>Session data</strong>: the messages you send and the roasts you receive, used to power history and shareable links.</li>
        <li><strong>Payment data</strong>: handled by Razorpay. We store the payment id, amount, currency, and status, but never your card details.</li>
      </ul>

      <h2 className="mt-6 font-display text-2xl">What we don&apos;t collect</h2>
      <ul className="list-disc pl-6 text-muted">
        <li>Card numbers, CVVs, or any payment-method details (Razorpay handles those).</li>
        <li>Precise location, contacts, or any device identifiers beyond the session cookie.</li>
      </ul>

      <h2 className="mt-6 font-display text-2xl">How we use it</h2>
      <p className="text-muted">
        To run the service. We do not sell your data. We do not show you ads. We log minimal request
        metadata for abuse prevention.
      </p>

      <h2 className="mt-6 font-display text-2xl">Your rights</h2>
      <p className="text-muted">
        You can delete your account and all associated data at any time. Email
        <a className="text-accent-3" href="mailto:support@roastgpt.app">support@roastgpt.app</a>.
      </p>

      <h2 className="mt-6 font-display text-2xl">Contact</h2>
      <p className="text-muted">
        Questions? <a className="text-accent-3" href="mailto:support@roastgpt.app">support@roastgpt.app</a>.
      </p>
    </article>
  );
}
