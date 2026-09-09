"use client";

import { useState } from "react";
import { AIExplanation } from "@/components/AIExplanation";
import { ErrorState } from "@/components/ErrorState";
import { LimitationList } from "@/components/LimitationList";
import { SeverityBadge } from "@/components/StatusBadge";
import {
  IngredientCategory,
  ProductAnalysisError,
  ProductCategory,
  ProductExplanationResponse,
  explainProduct,
} from "@/lib/api";
import { getOrCreateAppSession } from "@/lib/session";

const CATEGORY_OPTIONS: { value: ProductCategory; label: string }[] = [
  { value: "cleanser", label: "Cleanser" },
  { value: "toner", label: "Toner" },
  { value: "serum", label: "Serum" },
  { value: "moisturizer", label: "Moisturizer" },
  { value: "sunscreen", label: "Sunscreen" },
  { value: "exfoliant", label: "Exfoliant" },
  { value: "treatment", label: "Treatment" },
  { value: "other", label: "Other" },
];

export const INGREDIENT_CATEGORY_LABELS: Record<IngredientCategory, string> = {
  retinoid: "Retinoid",
  aha: "AHA",
  bha: "BHA",
  exfoliant: "Exfoliant",
  vitamin_c: "Vitamin C",
  antioxidant: "Antioxidant",
  humectant: "Humectant",
  occlusive: "Occlusive",
  barrier_support: "Barrier support",
  brightening: "Brightening",
  soothing_agent: "Soothing agent",
  sunscreen_filter: "Sunscreen filter",
  acne_treatment: "Acne treatment",
  preservative: "Preservative",
  fragrance: "Fragrance",
  other: "Other",
};

type Status = "idle" | "loading" | "success" | "error";

export function SingleProductAnalyzer() {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<ProductCategory | "">("");
  const [ingredients, setIngredients] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<ProductExplanationResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setErrorMessage(null);
    try {
      const sessionId = await getOrCreateAppSession();
      const response = await explainProduct({
        name,
        category: category || undefined,
        rawIngredientText: ingredients,
        sessionId,
      });
      setResult(response);
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof ProductAnalysisError
          ? err.message
          : "Analysis failed. Please try again.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Product name
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
            placeholder="e.g. Gentle Hydrating Serum"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Category (optional)
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as ProductCategory | "")}
            className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
          >
            <option value="">Unspecified</option>
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Ingredient list
          <textarea
            required
            rows={4}
            value={ingredients}
            onChange={(e) => setIngredients(e.target.value)}
            className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 font-mono text-sm dark:border-neutral-700"
            placeholder="Water, Niacinamide, Glycerin, Panthenol"
          />
        </label>

        <button
          type="submit"
          disabled={status === "loading"}
          className="self-start rounded-full bg-neutral-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
        >
          {status === "loading" ? "Analyzing…" : "Analyze Ingredients"}
        </button>
      </form>

      {status === "error" && errorMessage && <ErrorState message={errorMessage} />}

      {status === "success" && result && (
        <div className="flex flex-col gap-6">
          <div>
            <h2 className="mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
              Ingredients
            </h2>
            <ul className="flex flex-col divide-y divide-neutral-200 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
              {result.analysis.ingredients.map((ing, idx) => (
                <li
                  key={`${ing.raw_text}-${idx}`}
                  className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{ing.raw_text}</span>
                    {ing.ambiguous && (
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        Ambiguous -- could mean: {ing.candidates.join(", ")}.
                        Not automatically resolved.
                      </span>
                    )}
                    {!ing.matched && !ing.ambiguous && (
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        Not recognized -- no supported rule is available for
                        this ingredient.
                      </span>
                    )}
                  </div>
                  {ing.matched && ing.categories.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {ing.categories.map((cat) => (
                        <span
                          key={cat}
                          className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                        >
                          {INGREDIENT_CATEGORY_LABELS[cat] ?? cat}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {result.analysis.interactions.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Compatibility notes
              </h2>
              <ul className="flex flex-col gap-3">
                {result.analysis.interactions.map((interaction) => (
                  <li
                    key={interaction.rule_id ?? `${interaction.ingredient_a}-${interaction.ingredient_b}`}
                    className="rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <SeverityBadge severity={interaction.severity} />
                      <span className="text-neutral-500 dark:text-neutral-400">
                        {interaction.ingredient_a} + {interaction.ingredient_b}
                      </span>
                    </div>
                    <p>{interaction.message}</p>
                    {interaction.reason && (
                      <p className="mt-1 text-neutral-500 dark:text-neutral-400">
                        {interaction.reason}
                      </p>
                    )}
                    {interaction.source && (
                      <p className="mt-2 text-xs text-neutral-400 dark:text-neutral-500">
                        Source:{" "}
                        {interaction.source_url ? (
                          <a
                            href={interaction.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline"
                          >
                            {interaction.source}
                          </a>
                        ) : (
                          interaction.source
                        )}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.analysis.unknown_ingredients.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm dark:border-amber-900 dark:bg-amber-950/30">
              <p className="mb-1 font-medium text-amber-900 dark:text-amber-200">
                Unrecognized ingredients
              </p>
              <p className="text-amber-800/90 dark:text-amber-300/90">
                No supported rule is available for:{" "}
                {result.analysis.unknown_ingredients.join(", ")}.
              </p>
            </div>
          )}

          <LimitationList limitations={result.analysis.limitations} />

          <AIExplanation
            explanation={result.explanation}
            status={result.explanation_status}
            error={result.explanation_error}
          />
        </div>
      )}
    </div>
  );
}
