"use client";

import { useEffect } from "react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: Props) {
  useEffect(() => {
    console.error("[RoastGPT] Unhandled error:", error);
  }, [error]);

  return (
    <div className="card mx-auto max-w-xl text-center">
      <h1 className="font-display text-3xl font-bold gradient-text">
        Something caught fire that wasn&rsquo;t supposed to.
      </h1>
      <p className="mt-3 text-muted">
        The page hit an unexpected error. Your session (if any) is safe on the server.
      </p>
      {error?.message && (
        <p className="mt-2 text-xs text-muted/70 font-mono break-all">
          {error.message}
        </p>
      )}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <button onClick={reset} className="btn-primary text-sm">
          Try again
        </button>
        <a href="/" className="btn-ghost text-sm">
          Back to home
        </a>
      </div>
    </div>
  );
}
