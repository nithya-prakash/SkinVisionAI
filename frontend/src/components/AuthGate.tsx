"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { useCurrentUser } from "@/lib/useCurrentUser";

/** Wraps a session-scoped page (Skin Check, Compare, Routine, Copilot
 * Chat, History). Every one of those requires authentication now
 * (release-hardening follow-up) -- this is the one place that checks
 * and shows a consistent "sign in to continue" prompt, instead of each
 * page reimplementing the check and either silently failing or showing
 * a confusing 401-shaped error.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useCurrentUser();

  if (status === "loading") {
    return null;
  }

  if (status === "signed-out") {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-start gap-4 px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to continue</h1>
        <p className="text-neutral-600 dark:text-neutral-300">
          This page is tied to your account&apos;s session, so you&apos;ll need to sign in first.
        </p>
        <div className="flex gap-3">
          <Link
            href="/login"
            className="rounded-full bg-neutral-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="rounded-full border border-neutral-300 px-6 py-3 text-sm font-medium transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-900"
          >
            Sign up
          </Link>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
