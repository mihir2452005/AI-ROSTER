import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";
import HeaderAuth from "../components/HeaderAuth";
import ErrorBoundary from "../components/ErrorBoundary";
import ThemeProvider from "../components/ThemeProvider";
import ThemeToggle from "../components/ThemeToggle";

export const metadata: Metadata = {
  title: "RoastGPT — The Internet's Most Ruthless AI Roaster",
  description: "Get roasted by an AI with no chill, no filter, and no regrets.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://roastgpt.vercel.app"),
  openGraph: {
    title: "RoastGPT — The Internet's Most Ruthless AI Roaster",
    description: "Get roasted by an AI with no chill, no filter, and no regrets.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "RoastGPT — The Internet's Most Ruthless AI Roaster",
    description: "Get roasted by an AI with no chill, no filter, and no regrets.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Bricolage+Grotesque:600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <meta name="theme-color" content="#0a0a0a" />
      </head>
      <body className="min-h-screen font-sans">
        <ThemeProvider>
          <Toaster
            position="top-right"
            theme="dark"
            toastOptions={{
              className: "!bg-surface !text-text !border !border-border",
            }}
            richColors
            closeButton
          />
          <ErrorBoundary>
            <header className="sticky top-0 z-30 border-b border-border/60 bg-bg/80 backdrop-blur-md">
              <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
                <a href="/" className="flex items-center gap-2" aria-label="RoastGPT home">
                  <span className="text-2xl" aria-hidden="true">🔥</span>
                  <span className="font-display text-xl font-bold gradient-text">RoastGPT</span>
                </a>
                <nav className="flex items-center gap-2 text-sm" aria-label="Primary">
                  <a href="/leaderboard" className="btn-ghost hidden sm:inline">Leaderboard</a>
                  <a href="/pricing" className="btn-ghost hidden sm:inline">Pricing</a>
                  <ThemeToggle />
                  <HeaderAuth />
                </nav>
              </div>
            </header>
            <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
            <footer className="mx-auto max-w-6xl px-4 py-8 text-center text-xs text-muted">
              <p>RoastGPT — for entertainment only. No feelings were harmed in the making of this product. (Some were, though.)</p>
              <p className="mt-2">
                <a href="/privacy" className="hover:text-accent-2">Privacy</a>
                {" · "}
                <a href="/terms" className="hover:text-accent-2">Terms</a>
              </p>
            </footer>
          </ErrorBoundary>
        </ThemeProvider>
      </body>
    </html>
  );
}
