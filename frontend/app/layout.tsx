import type { Metadata } from "next";
import "./globals.css";
import HeaderAuth from "../components/HeaderAuth";

export const metadata: Metadata = {
  title: "RoastGPT — The Internet's Most Ruthless AI Roaster",
  description: "Get roasted by an AI with no chill, no filter, and no regrets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Bricolage+Grotesque:600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body className="min-h-screen font-sans">
        <header className="sticky top-0 z-30 border-b border-border/60 bg-bg/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <a href="/" className="flex items-center gap-2">
              <span className="text-2xl">🔥</span>
              <span className="font-display text-xl font-bold gradient-text">RoastGPT</span>
            </a>
            <nav className="flex items-center gap-2 text-sm">
              <a href="/leaderboard" className="btn-ghost hidden sm:inline">Leaderboard</a>
              <a href="/pricing" className="btn-ghost hidden sm:inline">Pricing</a>
              <HeaderAuth />
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 py-8 text-center text-xs text-muted">
          RoastGPT — for entertainment only. No feelings were harmed in the making of this product.
          (Some were, though.)
        </footer>
      </body>
    </html>
  );
}
