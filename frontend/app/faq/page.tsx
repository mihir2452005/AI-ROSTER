"use client";

import { useState } from "react";

const FAQ = [
  {
    q: "Is RoastGPT free to use?",
    a: "Yes — the first 5 messages per account are free, no card required. After that you can pick a Pro or Premium plan (monthly or yearly) to keep roasting. We also reset your free quota every billing cycle if you subscribe, and you can earn bonus free messages by sharing roasts or inviting friends.",
  },
  {
    q: "Will my roasts be public?",
    a: "By default, no. Your chat history is private. The one exception is when you click 'Share' on a roast — that creates an unlisted link. Anyone with the link can view that single conversation. You can revoke shared links at any time from your history page.",
  },
  {
    q: "What AI model is this running on?",
    a: "RoastGPT routes between OpenAI, Anthropic, and a self-hosted fallback depending on availability, latency, and your plan tier. We never log your full chat history on the model side — only the last few messages needed to generate the next roast. The first message of a session is always sent; we never train on your data.",
  },
  {
    q: "Can I get a refund?",
    a: "Within 7 days of your first paid charge, yes — email support@roastgpt.app from the address on your account and we'll process a full refund, no questions asked. After 7 days, we don't refund partial months, but you can cancel any time and keep access until the end of the current billing period.",
  },
  {
    q: "What happens if I delete my account?",
    a: "We soft-delete your account immediately: login is disabled, your email is anonymized, and your chat history is hidden from your own view. After 30 days the data is permanently purged from our primary database. Backups are rotated on a 7-day cycle, so residual data may live in cold backups for up to 30 days total.",
  },
  {
    q: "How do you handle abuse or harassment?",
    a: "Our safety layer filters out hate speech, sexual content, and personal data (phone numbers, addresses) before the model sees them. You can also report a single roast with the flag button — the report goes to a human moderator. We ban accounts that repeatedly try to extract slurs, doxxing info, or instructions for harm.",
  },
  {
    q: "Do you support voice or video?",
    a: "Not yet. Voice roasts and video are on the roadmap but not currently shipping — text-only for now. If you want early access, drop your email on the contact page and we'll let you know when it lands.",
  },
  {
    q: "Can I use RoastGPT for my own product?",
    a: "The consumer product is for personal use. If you want to embed roasts in your own app, newsletter, or community, see the /developers page for the API. The API has its own rate limits and a usage-based pricing tier.",
  },
  {
    q: "Where is my data stored?",
    a: "Application data lives on Neon (Postgres) in the US-East region. Static assets and chat thumbnails are on a CDN. We do not transfer your data outside of the regions required to operate the service. See /privacy for the full breakdown.",
  },
  {
    q: "How do I contact support?",
    a: "Use the /contact page, or email support@roastgpt.app. For security issues, use security@roastgpt.app — that inbox is monitored 24/7 and we have a 90-day disclosure policy.",
  },
];

export default function FaqPage() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <article className="prose prose-invert mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold">Frequently asked questions</h1>
      <p className="text-muted">
        Quick answers to the most common questions. If something is missing, drop a note on
        the <a className="text-accent-3" href="/contact">contact page</a>.
      </p>

      <div className="mt-6 divide-y divide-white/10 rounded-md border border-white/10 bg-surface/40">
        {FAQ.map((item, i) => {
          const isOpen = open === i;
          return (
            <div key={i}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left text-sm font-medium text-fg hover:bg-white/5"
              >
                <span>{item.q}</span>
                <span
                  aria-hidden
                  className={`text-accent-3 transition-transform ${isOpen ? "rotate-45" : ""}`}
                >
                  +
                </span>
              </button>
              {isOpen && (
                <div className="px-4 pb-4 text-sm text-muted">
                  {item.a}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </article>
  );
}
