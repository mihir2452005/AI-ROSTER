import Link from "next/link";

export default function NotFound() {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <div className="card max-w-md text-center">
        <div className="text-6xl">🧭</div>
        <h1 className="mt-4 font-display text-3xl font-bold">Wrong turn.</h1>
        <p className="mt-2 text-sm text-muted">
          We couldn&apos;t find that page. It might have been moved, deleted, or it never
          existed in the first place.
        </p>
        <div className="mt-4 flex justify-center gap-2">
          <Link href="/" className="btn-primary text-sm">Take me home</Link>
          <Link href="/leaderboard" className="btn-ghost text-sm">See leaderboard</Link>
        </div>
      </div>
    </div>
  );
}
