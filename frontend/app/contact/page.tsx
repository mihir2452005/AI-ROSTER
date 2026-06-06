"use client";

import { useState } from "react";
import { contactApi } from "@/lib/auth-api";

type FormState = {
  name: string;
  email: string;
  subject: string;
  message: string;
};

const EMPTY: FormState = { name: "", email: "", subject: "", message: "" };

export default function ContactPage() {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});

  function update<K extends keyof FormState>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function validate(): boolean {
    const next: Partial<Record<keyof FormState, string>> = {};
    if (form.name.trim().length < 2) next.name = "Name must be at least 2 characters.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) next.email = "Please enter a valid email address.";
    if (form.subject.trim().length < 3) next.subject = "Subject must be at least 3 characters.";
    if (form.message.trim().length < 10) next.message = "Please write at least 10 characters.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResult(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const res = await contactApi.submit(form);
      setResult({ ok: true, message: `Thanks! Your message was received (ticket #${res.id}). We'll reply to ${form.email}.` });
      setForm(EMPTY);
    } catch (err: any) {
      // Maintenance mode returns 503 — surface that nicely.
      if (err?.status === 503 || err?.data?.maintenance) {
        setResult({ ok: false, message: "RoastGPT is currently under maintenance. Please try again in a few minutes." });
      } else {
        setResult({ ok: false, message: err?.message || "Something went wrong. Please try again or email support@roastgpt.app." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <article className="prose prose-invert mx-auto max-w-2xl">
      <h1 className="font-display text-4xl font-bold">Contact us</h1>
      <p className="text-muted">
        Bug reports, feature ideas, partnership inquiries, or just a hello — drop a note below
        and we'll get back to you. Most replies go out within one business day.
      </p>

      {result && (
        <div
          role="status"
          className={`my-4 rounded-md border px-4 py-3 text-sm ${
            result.ok
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-100"
              : "border-rose-500/40 bg-rose-500/10 text-rose-100"
          }`}
        >
          {result.message}
        </div>
      )}

      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
        <Field
          id="name"
          label="Name"
          value={form.name}
          onChange={(v) => update("name", v)}
          error={errors.name}
          maxLength={100}
          autoComplete="name"
        />
        <Field
          id="email"
          type="email"
          label="Email"
          value={form.email}
          onChange={(v) => update("email", v)}
          error={errors.email}
          maxLength={200}
          autoComplete="email"
        />
        <Field
          id="subject"
          label="Subject"
          value={form.subject}
          onChange={(v) => update("subject", v)}
          error={errors.subject}
          maxLength={200}
        />
        <div>
          <label htmlFor="message" className="mb-1 block text-sm font-medium">
            Message
          </label>
          <textarea
            id="message"
            rows={6}
            value={form.message}
            onChange={(e) => update("message", e.target.value)}
            maxLength={5000}
            aria-invalid={!!errors.message}
            className={`w-full rounded-md border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent-3 ${
              errors.message ? "border-rose-500" : "border-white/10"
            }`}
            placeholder="Tell us what's on your mind…"
          />
          <FieldMeta error={errors.message} max={5000} value={form.message} />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent-3 px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Sending…" : "Send message"}
        </button>
      </form>

      <h2 className="mt-10 font-display text-2xl">Other ways to reach us</h2>
      <ul className="text-muted">
        <li>Email: <a className="text-accent-3" href="mailto:support@roastgpt.app">support@roastgpt.app</a></li>
        <li>Status page: <a className="text-accent-3" href="/status">/status</a></li>
        <li>Security issues: <a className="text-accent-3" href="mailto:security@roastgpt.app">security@roastgpt.app</a></li>
      </ul>
    </article>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  error,
  maxLength,
  autoComplete,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  error?: string;
  maxLength?: number;
  autoComplete?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={maxLength}
        autoComplete={autoComplete}
        aria-invalid={!!error}
        className={`w-full rounded-md border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent-3 ${
          error ? "border-rose-500" : "border-white/10"
        }`}
      />
      <FieldMeta error={error} max={maxLength} value={value} />
    </div>
  );
}

function FieldMeta({ error, max, value }: { error?: string; max?: number; value: string }) {
  if (error) {
    return <p className="mt-1 text-xs text-rose-400">{error}</p>;
  }
  if (max && max - value.length < 50) {
    return <p className="mt-1 text-xs text-muted">{max - value.length} characters left</p>;
  }
  return null;
}
