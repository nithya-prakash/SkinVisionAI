"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { ErrorState } from "@/components/ErrorState";
import { LimitationList } from "@/components/LimitationList";
import {
  AnalysisDetailResponse,
  AnalysisNotFoundError,
  ObservationFeature,
  ObservationLevel,
  VisualAnalysisRequestError,
  getAnalysis,
  runVisualAnalysis,
} from "@/lib/api";

const FEATURE_LABELS: Record<ObservationFeature, string> = {
  redness: "Visible redness",
  dryness: "Apparent dryness",
  visible_texture: "Visible texture",
  shine_oiliness: "Visible shine",
  uneven_tone: "Visible uneven tone",
  visible_spots_marks: "Visible spots/marks",
};

const LEVEL_LABELS: Record<ObservationLevel, string> = {
  minimal: "Minimal",
  mild: "Mild",
  moderate: "Moderate",
  pronounced: "Pronounced",
};

const LEVEL_STYLES: Record<ObservationLevel, string> = {
  minimal: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300",
  mild: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  moderate: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  pronounced: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200",
};

type LoadState = "loading" | "loaded" | "error";

export function ResultsClient({ analysisId }: { analysisId: string }) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [analysis, setAnalysis] = useState<AnalysisDetailResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [runningVisualAnalysis, setRunningVisualAnalysis] = useState(false);

  const load = useCallback(async () => {
    setLoadState("loading");
    setErrorMessage(null);
    try {
      // Retrieval only -- never recomputes anything (Phase 8).
      const response = await getAnalysis(analysisId);
      setAnalysis(response);
      setLoadState("loaded");
    } catch (err) {
      const message =
        err instanceof AnalysisNotFoundError
          ? "No analysis was found for this id."
          : "Could not load this analysis. Please try again.";
      setErrorMessage(message);
      setLoadState("error");
    }
  }, [analysisId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function runVisualAnalysisNow() {
    setRunningVisualAnalysis(true);
    setErrorMessage(null);
    try {
      await runVisualAnalysis(analysisId);
      await load(); // re-fetch the persisted result rather than trusting the POST response alone
    } catch (err) {
      const message =
        err instanceof VisualAnalysisRequestError
          ? err.message
          : "Visual analysis failed. Please try again.";
      setErrorMessage(message);
    } finally {
      setRunningVisualAnalysis(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Visual Observations</h1>

      {loadState === "loading" && (
        <p className="text-neutral-500 dark:text-neutral-400">Loading&hellip;</p>
      )}

      {loadState === "error" && errorMessage && (
        <ErrorState message={errorMessage} onRetry={load} />
      )}

      {loadState === "loaded" && analysis && (
        <div className="flex flex-col gap-6">
          {errorMessage && <ErrorState message={errorMessage} />}

          {analysis.status === "quality_rejected" && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <p className="font-medium">
                This image did not pass the quality check, so visual analysis
                was never run.
              </p>
              {analysis.image.quality_result?.issues && (
                <ul className="mt-2 list-disc pl-5">
                  {analysis.image.quality_result.issues.map((issue) => (
                    <li key={issue}>{issue.replace(/_/g, " ")}</li>
                  ))}
                </ul>
              )}
              <p className="mt-3">
                <Link href="/analyze" className="underline underline-offset-2">
                  Upload a different photo
                </Link>
              </p>
            </div>
          )}

          {analysis.status === "ready_for_visual_analysis" && (
            <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
              <p>This image passed the quality check. Run visual analysis to see observations.</p>
              <button
                onClick={runVisualAnalysisNow}
                disabled={runningVisualAnalysis}
                className="self-start rounded-full bg-neutral-900 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                {runningVisualAnalysis ? "Running non-diagnostic visual analysis…" : "Run Visual Analysis"}
              </button>
            </div>
          )}

          {analysis.status === "analyzing" && (
            <p className="text-neutral-500 dark:text-neutral-400">
              Visual analysis is in progress&hellip;
            </p>
          )}

          {analysis.status === "failed" && (
            <ErrorState
              message="Visual analysis failed for this image."
              onRetry={runVisualAnalysisNow}
              retryLabel={runningVisualAnalysis ? "Retrying…" : "Try again"}
            />
          )}

          {analysis.status === "completed" && analysis.visual_analysis && (
            <>
              <ul className="flex flex-col divide-y divide-neutral-200 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
                {analysis.visual_analysis.observations.map((obs) => (
                  <li
                    key={obs.feature}
                    className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex flex-col">
                      <span className="font-medium">{FEATURE_LABELS[obs.feature]}</span>
                      {obs.note && (
                        <span className="text-xs text-neutral-500 dark:text-neutral-400">
                          {obs.note}
                        </span>
                      )}
                      <span className="text-xs text-neutral-400 dark:text-neutral-500">
                        Method: {obs.method}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-neutral-400 dark:text-neutral-500">
                        signal {obs.score.toFixed(2)} &middot; heuristic confidence{" "}
                        {obs.confidence.toFixed(2)}
                      </span>
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-medium ${LEVEL_STYLES[obs.level]}`}
                      >
                        {LEVEL_LABELS[obs.level]}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>

              <LimitationList limitations={analysis.visual_analysis.limitations} />

              <button
                onClick={runVisualAnalysisNow}
                disabled={runningVisualAnalysis}
                className="self-start rounded-full border border-neutral-300 px-6 py-3 text-sm font-medium transition-colors hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
              >
                {runningVisualAnalysis ? "Re-running…" : "Re-run analysis"}
              </button>
            </>
          )}
        </div>
      )}

      <Disclaimer className="mt-auto" />
    </main>
  );
}
