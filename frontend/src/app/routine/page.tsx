"use client";

import Link from "next/link";
import { useState } from "react";
import { AIExplanation } from "@/components/AIExplanation";
import { Disclaimer, DISCLAIMER } from "@/components/Disclaimer";
import { ErrorState } from "@/components/ErrorState";
import { LimitationList } from "@/components/LimitationList";
import { SeverityBadge, StatusBadge } from "@/components/StatusBadge";
import {
  IngredientCategory,
  ProductAnalysisError,
  ProductCategory,
  RoutineExplanationResponse,
  RoutineProductInput,
  TimeOfDayPreference,
  explainRoutine,
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

const TIME_OPTIONS: { value: TimeOfDayPreference; label: string }[] = [
  { value: "unspecified", label: "Unspecified" },
  { value: "AM", label: "AM only" },
  { value: "PM", label: "PM only" },
  { value: "AM_AND_PM", label: "AM & PM" },
];

const INGREDIENT_CATEGORY_LABELS: Record<IngredientCategory, string> = {
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

type FormProduct = {
  productName: string;
  rawIngredients: string;
  category: ProductCategory | "";
  timeOfDay: TimeOfDayPreference;
};

const EMPTY_PRODUCT: FormProduct = {
  productName: "",
  rawIngredients: "",
  category: "",
  timeOfDay: "unspecified",
};

type Status = "idle" | "loading" | "success" | "error";

export default function RoutinePage() {
  const [products, setProducts] = useState<FormProduct[]>([{ ...EMPTY_PRODUCT }]);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<RoutineExplanationResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [saveToHistory, setSaveToHistory] = useState(false);

  function updateProduct(index: number, patch: Partial<FormProduct>) {
    setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function addProduct() {
    setProducts((prev) => [...prev, { ...EMPTY_PRODUCT }]);
  }

  function removeProduct(index: number) {
    setProducts((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setErrorMessage(null);
    try {
      const input: RoutineProductInput[] = products.map((p) => ({
        productName: p.productName,
        rawIngredients: p.rawIngredients,
        category: p.category || undefined,
        timeOfDay: p.timeOfDay,
      }));
      const sessionId = await getOrCreateAppSession();
      const response = await explainRoutine(input, { sessionId, persist: saveToHistory });
      setResult(response);
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof ProductAnalysisError
          ? err.message
          : "Routine analysis failed. Please try again.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Routine Builder</h1>
      <p className="text-neutral-600 dark:text-neutral-300">
        Enter the products in your routine to see overlapping actives,
        compatibility notes across products, and a suggested AM/PM order.
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {products.map((product, index) => (
          <div
            key={index}
            className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Product {index + 1}
              </span>
              {products.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeProduct(index)}
                  className="text-xs text-neutral-400 hover:text-red-500"
                >
                  Remove
                </button>
              )}
            </div>

            <input
              type="text"
              required
              value={product.productName}
              onChange={(e) => updateProduct(index, { productName: e.target.value })}
              placeholder="Product name, e.g. Retinol Serum"
              className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700"
            />

            <textarea
              required
              rows={2}
              value={product.rawIngredients}
              onChange={(e) => updateProduct(index, { rawIngredients: e.target.value })}
              placeholder="Ingredient list, e.g. Water, Retinol, Glycerin"
              className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 font-mono text-sm dark:border-neutral-700"
            />

            <div className="flex gap-3">
              <select
                value={product.category}
                onChange={(e) =>
                  updateProduct(index, { category: e.target.value as ProductCategory | "" })
                }
                aria-label={`Category for product ${index + 1}`}
                className="flex-1 rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700"
              >
                <option value="">Category unspecified</option>
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>

              <select
                value={product.timeOfDay}
                onChange={(e) =>
                  updateProduct(index, { timeOfDay: e.target.value as TimeOfDayPreference })
                }
                aria-label={`Time of day for product ${index + 1}`}
                className="flex-1 rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700"
              >
                {TIME_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ))}

        <label className="flex w-fit items-center gap-2 text-sm text-neutral-600 dark:text-neutral-300">
          <input
            type="checkbox"
            checked={saveToHistory}
            onChange={(e) => setSaveToHistory(e.target.checked)}
            className="h-4 w-4 rounded border-neutral-300 dark:border-neutral-700"
          />
          Save this result to your session history
        </label>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={addProduct}
            className="rounded-full border border-neutral-300 px-5 py-2 text-sm font-medium hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-900"
          >
            + Add another product
          </button>
          <button
            type="submit"
            disabled={status === "loading"}
            className="rounded-full bg-neutral-900 px-6 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
          >
            {status === "loading" ? "Analyzing…" : "Analyze Routine"}
          </button>
        </div>
      </form>

      {status === "error" && errorMessage && <ErrorState message={errorMessage} />}

      {status === "success" && result && (
        <div className="flex flex-col gap-6">
          {result.analysis.overlapping_actives.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Overlapping actives
              </h2>
              <ul className="flex flex-col gap-3">
                {result.analysis.overlapping_actives.map((overlap) => (
                  <li
                    key={overlap.ingredient}
                    className="rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                  >
                    <p className="font-medium">
                      {overlap.ingredient.replace(/_/g, " ")} appears in{" "}
                      {overlap.count} products: {overlap.products.join(", ")}
                    </p>
                    <p className="mt-1 text-neutral-500 dark:text-neutral-400">
                      {overlap.message}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.analysis.interactions.length > 0 && (
            <div>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Compatibility notes
                <StatusBadge label="Rule · sourced" tone="neutral" />
              </h2>
              <ul className="flex flex-col gap-3">
                {result.analysis.interactions.map((interaction) => (
                  <li
                    key={interaction.rule_id ?? `${interaction.ingredient_a}-${interaction.ingredient_b}`}
                    className="rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={interaction.severity} />
                      <span className="text-neutral-500 dark:text-neutral-400">
                        {interaction.ingredient_a} + {interaction.ingredient_b} (
                        {interaction.products.join(", ")})
                      </span>
                    </div>
                    <p>{interaction.message}</p>
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

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Suggested AM order
                <StatusBadge label="Suggestion · heuristic" tone="info" />
              </h2>
              {result.analysis.suggested_am.length > 0 ? (
                <ol className="flex flex-col gap-1 rounded-lg border border-neutral-200 p-3 text-sm dark:border-neutral-800">
                  {result.analysis.suggested_am.map((step, i) => (
                    <li key={step.product_name}>
                      {i + 1}. {step.product_name}{" "}
                      <span className="text-neutral-400">({step.category})</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-neutral-400">No AM steps suggested.</p>
              )}
            </div>
            <div>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Suggested PM order
                <StatusBadge label="Suggestion · heuristic" tone="info" />
              </h2>
              {result.analysis.suggested_pm.length > 0 ? (
                <ol className="flex flex-col gap-1 rounded-lg border border-neutral-200 p-3 text-sm dark:border-neutral-800">
                  {result.analysis.suggested_pm.map((step, i) => (
                    <li key={step.product_name}>
                      {i + 1}. {step.product_name}{" "}
                      <span className="text-neutral-400">({step.category})</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-neutral-400">No PM steps suggested.</p>
              )}
            </div>
          </div>

          {result.analysis.unscheduled_products.length > 0 && (
            <div className="rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
              <p className="mb-1 font-medium">Not scheduled</p>
              <ul className="list-disc pl-5 text-neutral-500 dark:text-neutral-400">
                {result.analysis.unscheduled_products.map((item) => (
                  <li key={item.product_name}>
                    {item.product_name}: {item.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <h2 className="mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
              Detected ingredients by product
            </h2>
            <ul className="flex flex-col gap-3">
              {result.analysis.products.map((product) => (
                <li
                  key={product.product_name}
                  className="rounded-lg border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
                >
                  <p className="font-medium">{product.product_name}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {product.normalized_ingredients.map((ing, i) => (
                      <span
                        key={`${ing.raw_text}-${i}`}
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          ing.matched
                            ? "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                            : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                        }`}
                      >
                        {ing.raw_text}
                        {ing.categories.length > 0 &&
                          ` (${ing.categories.map((c) => INGREDIENT_CATEGORY_LABELS[c] ?? c).join(", ")})`}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <LimitationList limitations={result.analysis.limitations} />

          {result.analysis.id && (
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              Saved to your session history.{" "}
              <Link href="/history" className="underline underline-offset-2">
                View history
              </Link>
              .
            </p>
          )}

          <AIExplanation
            explanation={result.explanation}
            status={result.explanation_status}
            error={result.explanation_error}
          />
        </div>
      )}

      <Disclaimer className="mt-auto" text={DISCLAIMER} />
    </main>
  );
}
