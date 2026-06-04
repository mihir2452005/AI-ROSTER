import Link from "next/link";

export default function GlobalNotFound() {
  return (
    <div className="card mx-auto max-w-xl text-center">
      <h1 className="font-display text-5xl font-extrabold gradient-text">
        404
      </h1>
      <p className="mt-3 text-lg text-muted">
        That page doesn&rsquo;t exist. It probably fled the roaster.
      </p>
      <Link href="/" className="btn-primary mt-6 inline-flex text-sm">
        Back to home
      </Link>
    </div>
  );
}
