export default function ChatLoading() {
  return (
    <div className="card flex min-h-[70vh] flex-col p-0">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="h-4 w-32 animate-pulse rounded bg-border/60" />
        <div className="h-6 w-16 animate-pulse rounded bg-border/60" />
      </div>
      <div className="flex-1 space-y-4 px-4 py-6">
        <div className="h-20 w-2/3 animate-pulse rounded-xl bg-border/40" />
        <div className="ml-auto h-10 w-1/3 animate-pulse rounded-xl bg-border/40" />
        <div className="h-16 w-3/4 animate-pulse rounded-xl bg-border/40" />
      </div>
      <div className="border-t border-border/60 p-3">
        <div className="h-10 w-full animate-pulse rounded bg-border/40" />
      </div>
    </div>
  );
}
