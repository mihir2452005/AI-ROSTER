export default function Loading() {
  return (
    <div className="mx-auto max-w-md text-center text-muted">
      <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <p className="mt-3 text-sm">Loading…</p>
    </div>
  );
}
