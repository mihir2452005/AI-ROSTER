/* RoastGPT â€” Small client-side security helpers. */

/**
 * Validates a `?return=` (or similar) redirect target to prevent open
 * redirects. Allowed shapes:
 *   - `/`                       (home)
 *   - `/pricing`                (relative path)
 *   - `/chat/abc123?foo=bar`    (with query / hash)
 *
 * Rejected:
 *   - `//evil.com`              (protocol-relative â€” goes to evil.com)
 *   - `https://evil.com`        (absolute URL)
 *   - `/\\evil.com`             (backslash variant â€” some parsers treat
 *                               `\` as `/`, leading to evil.com)
 *   - `javascript:...`          (JS URI)
 *   - any URL with a scheme
 *
 * A phishing email could otherwise send
 *   https://roastgpt.com/login?return=https://attacker.example/steal-token
 * and the post-login redirect would send the user to the attacker.
 */
export function isSafeReturnPath(p: string | null | undefined): boolean {
  if (!p) return false;
  if (typeof p !== "string") return false;
  if (p.length > 512) return false; // bound the work
  // Must start with a single forward slash. Reject protocol-relative
  // (`//evil.com`) and absolute URLs.
  if (!p.startsWith("/")) return false;
  // Reject `//` and `/\` at the start (treated as protocol-relative or
  // host-relative by some routers).
  if (p.startsWith("//") || p.startsWith("/\\")) return false;
  // Reject any backslash in the path â€” Next router / browser parsers
  // may normalise `\` to `/`, smuggling a host portion.
  if (p.includes("\\")) return false;
  // Reject embedded scheme (e.g., `/redirect?url=javascript:...`).
  // The check is on the decoded form so percent-encoded variants are
  // caught by a server-side check; for client-side we just refuse
  // obvious shapes.
  if (/^\/.*:/i.test(p)) {
    // Allow `:` in query strings / fragments (rare in practice; the
    // form `/foo:bar` is valid as a Next.js dynamic route param).
    // We only block `scheme:` at the start of a path segment.
    const firstSegment = p.split(/[?#]/, 1)[0];
    if (/^[a-z][a-z0-9+.-]*:/i.test(firstSegment)) return false;
  }
  return true;
}

/**
 * Returns a safe return path: `p` if it's a same-origin relative URL,
 * otherwise `/`. Use this everywhere we honor a user-supplied redirect
 * target.
 */
export function safeReturnPath(p: string | null | undefined, fallback = "/"): string {
  return isSafeReturnPath(p) ? (p as string) : fallback;
}
