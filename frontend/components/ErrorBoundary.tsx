"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * App-level error boundary. Catches render-time exceptions so the
 * user gets a friendly "something went wrong" page instead of a
 * blank screen. Logs to the console so the error is visible in
 * dev. In prod the message is intentionally generic â€” we never
 * leak the underlying error to the user.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    if (typeof console !== "undefined") {
      console.error("RoastGPT error boundary caught:", error, info?.componentStack);
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="grid min-h-[60vh] place-items-center p-6">
          <div className="card max-w-md text-center">
            <h1 className="font-display text-2xl font-bold gradient-text">
              Something went off the rails.
            </h1>
            <p className="mt-2 text-sm text-muted">
              The page hit an unexpected error. Reloading usually fixes it.
            </p>
            <button
              onClick={() => {
                if (typeof window !== "undefined") window.location.reload();
              }}
              className="btn-primary mt-4 text-sm"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
