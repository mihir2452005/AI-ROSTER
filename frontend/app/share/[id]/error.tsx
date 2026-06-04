"use client";

import { useEffect } from "react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ShareError({ error, reset }: Props) {
  useEffect(() => {
    console.error("[RoastGPT] Share page error:", error);
  }, [error]);

  return (
    <div className="card mx-auto max-w-xl text-center">
      <h1 className="font-display text-3xl font-bold gradient-text">
        Couldn&rsquo;t load this roast.
      </h1>
      <p className="mt-3 text-muted">
        The session may have expired, or the server is unreachable.
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
          Get roasted yourself
        </a>
      </div>
    </div>
  );
}
