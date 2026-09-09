import { Explanation, ExplanationStatus, RuleSeverity } from "@/lib/api";

const SEVERITY_LABELS: Record<RuleSeverity, string> = {
  incompatibility: "Incompatibility",
  caution: "Caution",
  informational: "Informational",
  no_known_conflict: "No known conflict",
};

const SEVERITY_STYLES: Record<RuleSeverity, string> = {
  incompatibility: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  caution: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  informational: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  no_known_conflict:
    "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300",
};

function AIBadge() {
  return (
    <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-950 dark:text-violet-300">
      AI-generated
    </span>
  );
}

/**
 * Renders the AI explanation for a deterministic analysis result. Visually
 * distinct (violet accent) from the deterministic sections above it, so
 * it's always clear which parts of the page are computed by rules/data
 * and which are narrative text from the LLM. The LLM never supplies
 * severity, source, or citation -- those values here are the same
 * deterministic values already shown above; only the "explanation" prose
 * on each item comes from the model.
 */
export function AIExplanation({
  explanation,
  status,
  error,
}: {
  explanation: Explanation | null;
  status: ExplanationStatus;
  error: string | null;
}) {
  if (status === "unavailable" || !explanation) {
    return (
      <div className="rounded-lg border border-dashed border-violet-300 bg-violet-50/50 px-4 py-3 text-sm text-violet-700 dark:border-violet-900 dark:bg-violet-950/30 dark:text-violet-300">
        <div className="mb-1 flex items-center gap-2">
          <AIBadge />
          <span className="font-medium">AI explanation is currently unavailable</span>
        </div>
        <p className="text-violet-600/80 dark:text-violet-400/80">
          {error ?? "The deterministic analysis above is unaffected and complete."}
        </p>
      </div>
    );
  }

  const sources = Array.from(
    new Map(
      [...explanation.interactions_explained, ...explanation.overlap_explained]
        .filter((item) => item.source)
        .map((item) => [item.source, item.source_url]),
    ).entries(),
  );

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-violet-200 bg-violet-50/40 px-4 py-4 text-sm dark:border-violet-900 dark:bg-violet-950/20">
      <div className="flex items-center gap-2">
        <AIBadge />
        <h2 className="font-medium text-violet-900 dark:text-violet-200">AI Explanation</h2>
      </div>

      <div>
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-violet-500 dark:text-violet-400">
          Summary
        </h3>
        <p className="text-neutral-700 dark:text-neutral-200">{explanation.summary}</p>
      </div>

      {(explanation.interactions_explained.length > 0 ||
        explanation.overlap_explained.length > 0) && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-violet-500 dark:text-violet-400">
            Why this matters
          </h3>
          <ul className="flex flex-col gap-2">
            {explanation.interactions_explained.map((item) => (
              <li
                key={item.rule_id ?? `${item.ingredient_a}-${item.ingredient_b}`}
                className="rounded-md border border-violet-100 bg-white px-3 py-2 dark:border-violet-900/60 dark:bg-neutral-900"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[item.severity]}`}
                  >
                    {SEVERITY_LABELS[item.severity]}
                  </span>
                  <span className="text-xs text-neutral-500 dark:text-neutral-400">
                    {item.ingredient_a} + {item.ingredient_b}
                  </span>
                </div>
                <p className="text-neutral-700 dark:text-neutral-200">{item.explanation}</p>
              </li>
            ))}
            {explanation.overlap_explained.map((item) => (
              <li
                key={item.ingredient}
                className="rounded-md border border-violet-100 bg-white px-3 py-2 dark:border-violet-900/60 dark:bg-neutral-900"
              >
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  {item.ingredient.replace(/_/g, " ")} &middot; {item.products.join(", ")}
                </span>
                <p className="text-neutral-700 dark:text-neutral-200">{item.explanation}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(explanation.key_points.length > 0 || explanation.routine_notes.length > 0) && (
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-violet-500 dark:text-violet-400">
            What to know
          </h3>
          <ul className="list-disc pl-5 text-neutral-700 dark:text-neutral-200">
            {explanation.key_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
            {explanation.routine_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      {sources.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-violet-500 dark:text-violet-400">
            Sources
          </h3>
          <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-500 dark:text-neutral-400">
            {sources.map(([source, url]) => (
              <li key={source}>
                {url ? (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
                    {source}
                  </a>
                ) : (
                  source
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="border-t border-violet-100 pt-3 text-xs text-violet-600/80 dark:border-violet-900/60 dark:text-violet-400/80">
        {explanation.disclaimer}
      </p>
    </div>
  );
}
