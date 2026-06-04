"use client";

import { useEffect } from "react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ChatError({ error, reset }: Props) {
  useEffect(() => {
    console.error("[RoastGPT] Chat error:", error);
  }, [error]);

  return (
    <div className="card mx-auto max-w-xl text-center">
      <h1 className="font-display text-3xl font-bold gradient-text">
        The chat hiccuped.
      </h1>
      <p className="mt-3 text-muted">
        Couldn&rsquo;t load this roast session. It may have expired or the server is
        unreachable.
      </p>
      {error?.message && (
        <p className="mt-2 text-xs text-muted/70 font-mono break-all">
          {error.message}
        </p>
      )}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <button onClick={reset} className="btn-primary text-sm">
          Retry
        </button>
        <a href="/" className="btn-ghost text-sm">
          Start over
        </a>
      </div>
    </div>
  );
}
