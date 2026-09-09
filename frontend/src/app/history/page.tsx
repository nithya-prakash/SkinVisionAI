"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Disclaimer, DISCLAIMER } from "@/components/Disclaimer";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import {
  ProductAnalysisError,
  SessionAnalysisSummary,
  SessionChatSummary,
  SessionComparisonSummary,
  SessionProductSummary,
  SessionRoutineAnalysisSummary,
  listSessionAnalyses,
  listSessionChats,
  listSessionComparisons,
  listSessionProducts,
  listSessionRoutineAnalyses,
} from "@/lib/api";
import { getStoredSessionId, setStoredChatSessionId } from "@/lib/session";

const ANALYSIS_STATUS_LABELS: Record<SessionAnalysisSummary["status"], string> = {
  quality_rejected: "Rejected (image quality)",
  ready_for_visual_analysis: "Ready for analysis",
  analyzing: "Analyzing",
  completed: "Completed",
  failed: "Failed",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

interface HistoryData {
  analyses: SessionAnalysisSummary[];
  chats: SessionChatSummary[];
  products: SessionProductSummary[];
  routineAnalyses: SessionRoutineAnalysisSummary[];
  comparisons: SessionComparisonSummary[];
}

type Status = "idle" | "loading" | "success" | "error" | "no-session";

export default function HistoryPage() {
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<HistoryData | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const sessionId = getStoredSessionId();
    if (!sessionId) {
      setStatus("no-session");
      return;
    }
    setStatus("loading");
    setErrorMessage(null);
    try {
      const [analyses, chats, products, routineAnalyses, comparisons] = await Promise.all([
        listSessionAnalyses(sessionId),
        listSessionChats(sessionId),
        listSessionProducts(sessionId),
        listSessionRoutineAnalyses(sessionId),
        listSessionComparisons(sessionId),
      ]);
      setData({
        analyses: analyses.analyses,
        chats: chats.chats,
        products: products.products,
        routineAnalyses: routineAnalyses.routine_analyses,
        comparisons: comparisons.comparisons,
      });
      setStatus("success");
    } catch (err) {
      if (err instanceof ProductAnalysisError && err.code === "session_not_found") {
        // The stored session id is stale (e.g. a reset database) --
        // there is nothing to show, not an error to retry.
        setStatus("no-session");
        return;
      }
      const message =
        err instanceof ProductAnalysisError ? err.message : "Could not load your session history.";
      setErrorMessage(message);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  function resumeChat(chatSessionId: string) {
    setStoredChatSessionId(chatSessionId);
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-16">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Session History</h1>
        <p className="text-neutral-600 dark:text-neutral-300">
          Everything analyzed, compared, or asked in this browser session. Nothing here is
          shared across devices or tied to an account -- clearing your browser storage clears
          this history too.
        </p>
      </div>

      {status === "loading" && (
        <p className="text-sm text-neutral-400">Loading your history&hellip;</p>
      )}

      {status === "no-session" && (
        <EmptyState
          message="You don't have a session yet. Analyze a photo, a product, or a routine to start building history."
          action={
            <div className="flex flex-wrap gap-3">
              <Link href="/analyze" className="text-sm font-medium underline underline-offset-2">
                Analyze a photo
              </Link>
              <Link href="/compare" className="text-sm font-medium underline underline-offset-2">
                Analyze or compare products
              </Link>
              <Link href="/routine" className="text-sm font-medium underline underline-offset-2">
                Analyze a routine
              </Link>
            </div>
          }
        />
      )}

      {status === "error" && errorMessage && <ErrorState message={errorMessage} onRetry={load} />}

      {status === "success" && data && (
        <div className="flex flex-col gap-10">
          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Skin Analyses</h2>
            {data.analyses.length === 0 ? (
              <EmptyState message="No skin analyses yet." />
            ) : (
              <ul className="flex flex-col gap-2">
                {data.analyses.map((a) => (
                  <li key={a.id}>
                    <Link
                      href={`/results/${a.id}`}
                      className="flex items-center justify-between rounded-lg border border-neutral-200 px-4 py-3 text-sm transition-colors hover:border-neutral-400 dark:border-neutral-800 dark:hover:border-neutral-600"
                    >
                      <span>{ANALYSIS_STATUS_LABELS[a.status]}</span>
                      <span className="text-neutral-400 dark:text-neutral-500">
                        {formatDate(a.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">AI Assistant Chats</h2>
            {data.chats.length === 0 ? (
              <EmptyState message="No chat conversations yet." />
            ) : (
              <ul className="flex flex-col gap-2">
                {data.chats.map((c) => (
                  <li key={c.id}>
                    <Link
                      href="/chat"
                      onClick={() => resumeChat(c.id)}
                      className="flex items-center justify-between rounded-lg border border-neutral-200 px-4 py-3 text-sm transition-colors hover:border-neutral-400 dark:border-neutral-800 dark:hover:border-neutral-600"
                    >
                      <span>
                        {c.message_count} message{c.message_count === 1 ? "" : "s"}
                      </span>
                      <span className="text-neutral-400 dark:text-neutral-500">
                        {formatDate(c.updated_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Product Analyses</h2>
            {data.products.length === 0 ? (
              <EmptyState message="No single-product ingredient analyses yet." />
            ) : (
              <ul className="flex flex-col gap-2">
                {data.products.map((p) => (
                  <li
                    key={p.id}
                    className="flex items-center justify-between rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                  >
                    <div className="flex flex-col">
                      <span className="font-medium">{p.name}</span>
                      <span className="text-neutral-500 dark:text-neutral-400">
                        {p.interaction_count} interaction{p.interaction_count === 1 ? "" : "s"}
                        {p.unknown_ingredient_count > 0 &&
                          ` · ${p.unknown_ingredient_count} unrecognized ingredient${p.unknown_ingredient_count === 1 ? "" : "s"}`}
                      </span>
                    </div>
                    <span className="text-neutral-400 dark:text-neutral-500">
                      {formatDate(p.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Routine Analyses</h2>
            {data.routineAnalyses.length === 0 ? (
              <EmptyState message="No saved routine analyses yet. Check &ldquo;Save this result to your session history&rdquo; on the Routine page to keep one." />
            ) : (
              <ul className="flex flex-col gap-2">
                {data.routineAnalyses.map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                  >
                    <span>
                      {r.product_count} product{r.product_count === 1 ? "" : "s"} ·{" "}
                      {r.interaction_count} interaction{r.interaction_count === 1 ? "" : "s"}
                    </span>
                    <span className="text-neutral-400 dark:text-neutral-500">
                      {formatDate(r.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Product Comparisons</h2>
            {data.comparisons.length === 0 ? (
              <EmptyState message="No saved product comparisons yet. Check &ldquo;Save this result to your session history&rdquo; on the Compare page to keep one." />
            ) : (
              <ul className="flex flex-col gap-2">
                {data.comparisons.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-center justify-between rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                  >
                    <span>
                      {c.product_a_name} vs. {c.product_b_name} · {c.interaction_count}{" "}
                      interaction{c.interaction_count === 1 ? "" : "s"}
                    </span>
                    <span className="text-neutral-400 dark:text-neutral-500">
                      {formatDate(c.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      <Disclaimer className="mt-auto" text={DISCLAIMER} />
    </main>
  );
}
