"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { authApi } from "../../lib/auth-api";

function VerifyEmailInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("err");
      setMessage("Missing token. Use the link from your verification email.");
      return;
    }
    setStatus("loading");
    authApi.verifyEmail(token)
      .then((r) => {
        setStatus("ok");
        setMessage(r.message || "Email verified.");
        toast.success("Email verified");
        // Best-effort: refresh cached user so the header updates.
        try { authApi.me().catch(() => {}); } catch { /* ignore */ }
      })
      .catch((e) => {
        setStatus("err");
        setMessage(e?.message || "Verification failed. The link may have expired.");
        toast.error("Verification failed");
      });
  }, [token]);

  return (
    <div className="mx-auto max-w-md card">
      <h1 className="font-display text-2xl font-bold gradient-text">Verify your email</h1>
      {status === "loading" && (
        <p className="mt-4 text-muted">Verifying…</p>
      )}
      {status !== "loading" && (
        <p className={`mt-4 text-sm ${status === "ok" ? "text-success" : "text-accent"}`}>
          {message}
        </p>
      )}
      <div className="mt-6 flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => router.push("/account")}>Go to account</button>
        <Link href="/login" className="btn-ghost">Back to login</Link>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="text-muted">Loading…</div>}>
      <VerifyEmailInner />
    </Suspense>
  );
}
