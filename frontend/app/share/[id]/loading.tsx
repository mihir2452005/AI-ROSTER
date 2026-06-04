export default function ShareLoading() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 text-center">
        <div className="mx-auto h-6 w-32 animate-pulse rounded-full bg-border/40" />
        <div className="mx-auto mt-3 h-10 w-3/4 animate-pulse rounded bg-border/40" />
      </div>
      <div className="card mb-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i}>
              <div className="h-3 w-16 animate-pulse rounded bg-border/40" />
              <div className="mt-2 h-8 w-12 animate-pulse rounded bg-border/40" />
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}
          >
            <div className="h-12 w-2/3 animate-pulse rounded-xl bg-border/40" />
          </div>
        ))}
      </div>
    </div>
  );
}
