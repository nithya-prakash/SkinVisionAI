"use client";

import { useEffect, useState } from "react";
import { CurrentUser, getCurrentUser } from "./auth";

export type AuthStatus = "loading" | "signed-in" | "signed-out";

/** Checks sign-in status once on mount. Used by NavBar (to show the
 * right links) and by AuthGate (to block session-scoped pages) alike,
 * so there's one place that calls `GET /api/auth/me`, not one per
 * consumer.
 */
export function useCurrentUser(): { status: AuthStatus; user: CurrentUser | null; refresh: () => void } {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((current) => {
        if (cancelled) return;
        setUser(current);
        setStatus(current ? "signed-in" : "signed-out");
      })
      .catch(() => {
        if (cancelled) return;
        setUser(null);
        setStatus("signed-out");
      });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  function refresh() {
    setStatus("loading");
    setNonce((n) => n + 1);
  }

  return { status, user, refresh };
}
