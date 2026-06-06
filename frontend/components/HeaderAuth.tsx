"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  authApi,
  cacheUser,
  clearTokens,
  getAccessToken,
  getCachedUser,
  getStoredTokenVersion,
  type User,
} from "../lib/auth-api";
import { NotificationBell } from "./NotificationBell";

// Broadcast channel name used by other parts of the app to tell
// HeaderAuth to refetch. The pricing page fires this on successful
// payment so the "â­ Subscribe" badge disappears without a full
// page reload.
const REFRESH_EVENT = "roastgpt:auth-refresh";

export default function HeaderAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);

  function refetch() {
    if (!getAccessToken()) {
      setUser(null);
      setChecked(true);
      return;
    }
    // Show the cached user instantly.
    const cached = getCachedUser();
    if (cached) setUser(cached);
    // Refetch the canonical user from the server. Cross-check
    // `token_version` to detect cross-tab/cross-device token
    // invalidation.
    const cachedVer = getStoredTokenVersion();
    authApi
      .me()
      .then((u) => {
        if (cached && cachedVer !== 0 && u.token_version !== cachedVer) {
          // Token was revoked in another tab/device. Force re-auth.
          clearTokens();
          setUser(null);
          return;
        }
        cacheUser(u);
        setUser(u);
      })
      .catch(() => { /* not logged in / token expired */ })
      .finally(() => setChecked(true));
  }

  useEffect(() => {
    refetch();
    // Re-run on any cross-component auth-refresh signal. This is how
    // the pricing page tells us "payment went through, please drop the
    // Subscribe badge" without a hard reload.
    if (typeof window !== "undefined") {
      const handler = () => refetch();
      window.addEventListener(REFRESH_EVENT, handler);
      return () => window.removeEventListener(REFRESH_EVENT, handler);
    }
  }, []);

  if (!checked) return <div className="w-32" />;

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Link href="/login" className="btn-ghost text-sm">Sign in</Link>
        <Link href="/register" className="btn-primary text-sm">Sign up</Link>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      {!user.has_active_subscription && (
        <Link
          href="/pricing"
          className="rounded-md bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1.5 text-xs font-semibold text-white"
        >
          â­ Subscribe
        </Link>
      )}
      <NotificationBell />
      {user.is_admin && (
        <Link href="/admin" className="btn-ghost text-sm">Admin</Link>
      )}
      <Link href="/history" className="btn-ghost text-sm hidden sm:inline">History</Link>
      <Link href="/account" className="flex items-center gap-2 hover:opacity-80">
        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold">
          {(user.full_name || user.email)[0].toUpperCase()}
        </div>
        <span className="hidden sm:inline">{user.full_name || user.email.split("@")[0]}</span>
      </Link>
    </div>
  );
}
