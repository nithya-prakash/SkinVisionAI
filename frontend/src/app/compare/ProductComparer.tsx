"use client";

import Link from "next/link";
import { useState } from "react";
import { AIExplanation } from "@/components/AIExplanation";
import { ErrorState } from "@/components/ErrorState";
import { LimitationList } from "@/components/LimitationList";
import { SeverityBadge } from "@/components/StatusBadge";
import {
  ComparisonExplanationResponse,
  ProductAnalysisError,
  ProductCategory,
  explainComparison,
} from "@/lib/api";
import { getOrCreateAppSession } from "@/lib/session";
import { INGREDIENT_CATEGORY_LABELS } from "./SingleProductAnalyzer";

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

type FormProduct = {
  name: string;
  category: ProductCategory | "";
  ingredients: string;
};

const EMPTY: FormProduct = { name: "", category: "", ingredients: "" };

type Status = "idle" | "loading" | "success" | "error";

function prettify(name: string): string {
  return name.replace(/_/g, " ");
}

export function ProductComparer() {
  const [productA, setProductA] = useState<FormProduct>({ ...EMPTY });
  const [productB, setProductB] = useState<FormProduct>({ ...EMPTY });
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<ComparisonExplanationResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [saveToHistory, setSaveToHistory] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setErrorMessage(null);
    try {
      const sessionId = await getOrCreateAppSession();
      const response = await explainComparison(
        {
          name: productA.name,
          category: productA.category || undefined,
          rawIngredientText: productA.ingredients,
        },
        {
          name: productB.name,
          category: productB.category || undefined,
          rawIngredientText: productB.ingredients,
        },
        { sessionId, persist: saveToHistory },
      );
      setResult(response);
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof ProductAnalysisError
          ? err.message
          : "Comparison failed. Please try again.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {(
            [
              ["A", productA, setProductA],
              ["B", productB, setProductB],
            ] as const
          ).map(([label, value, setValue]) => (
            <div
              key={label}
              className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800"
            >
              <span className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Product {label}
              </span>
              <input
                type="text"
                required
                value={value.name}
                onChange={(e) => setValue({ ...value, name: e.target.value })}
                placeholder="Product name"
                aria-label={`Product ${label} name`}
                className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700"
              />
              <select
                value={value.category}
                onChange={(e) =>
                  setValue({ ...value, category: e.target.value as ProductCategory | "" })
                }
                aria-label={`Product ${label} category`}
                className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700"
              >
                <option value="">Category unspecified</option>
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <textarea
                required
                rows={4}
                value={value.ingredients}
                onChange={(e) => setValue({ ...value, ingredients: e.target.value })}
                placeholder="Ingredient list"
                aria-label={`Product ${label} ingredient list`}
                className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 font-mono text-sm dark:border-neutral-700"
              />
            </div>
          ))}
        </div>

        <label className="flex w-fit items-center gap-2 text-sm text-neutral-600 dark:text-neutral-300">
          <input
            type="checkbox"
            checked={saveToHistory}
            onChange={(e) => setSaveToHistory(e.target.checked)}
            className="h-4 w-4 rounded border-neutral-300 dark:border-neutral-700"
          />
          Save this result to your session history
        </label>

        <button
          type="submit"
          disabled={status === "loading"}
          className="self-start rounded-full bg-neutral-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
        >
          {status === "loading" ? "Comparing…" : "Compare Products"}
        </button>
      </form>

      {status === "error" && errorMessage && <ErrorState message={errorMessage} />}

      {status === "success" && result && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <h2 className="mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Shared ingredients
              </h2>
              {result.analysis.shared_ingredients.length > 0 ? (
                <ul className="flex flex-wrap gap-1">
                  {result.analysis.shared_ingredients.map((ing) => (
                    <li
                      key={ing}
                      className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                    >
                      {prettify(ing)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-neutral-400">None</p>
              )}
            </div>
            <div>
              <h2 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                <span className="rounded bg-neutral-900 px-1.5 py-0.5 text-[10px] font-semibold text-white dark:bg-white dark:text-black">
                  A
                </span>
                Only in {result.analysis.product_a_name}
              </h2>
              {result.analysis.only_in_a.length > 0 ? (
                <ul className="flex flex-wrap gap-1">
                  {result.analysis.only_in_a.map((ing) => (
                    <li
                      key={ing}
                      className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                    >
                      {prettify(ing)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-neutral-400">None</p>
              )}
            </div>
            <div>
              <h2 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                <span className="rounded bg-neutral-900 px-1.5 py-0.5 text-[10px] font-semibold text-white dark:bg-white dark:text-black">
                  B
                </span>
                Only in {result.analysis.product_b_name}
              </h2>
              {result.analysis.only_in_b.length > 0 ? (
                <ul className="flex flex-wrap gap-1">
                  {result.analysis.only_in_b.map((ing) => (
                    <li
                      key={ing}
                      className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                    >
                      {prettify(ing)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-neutral-400">None</p>
              )}
            </div>
          </div>

          {result.analysis.shared_categories.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Shared active categories
              </h2>
              <ul className="flex flex-wrap gap-1">
                {result.analysis.shared_categories.map((cat) => (
                  <li
                    key={cat}
                    className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                  >
                    {INGREDIENT_CATEGORY_LABELS[cat] ?? cat}
                  </li>
                ))}
              </ul>
            </div>
          )}

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

          {(result.analysis.unknown_ingredients_a.length > 0 || result.analysis.unknown_ingredients_b.length > 0) && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm dark:border-amber-900 dark:bg-amber-950/30">
              <p className="mb-1 font-medium text-amber-900 dark:text-amber-200">
                Unrecognized ingredients
              </p>
              {result.analysis.unknown_ingredients_a.length > 0 && (
                <p className="text-amber-800/90 dark:text-amber-300/90">
                  {result.analysis.product_a_name}: {result.analysis.unknown_ingredients_a.join(", ")}
                </p>
              )}
              {result.analysis.unknown_ingredients_b.length > 0 && (
                <p className="text-amber-800/90 dark:text-amber-300/90">
                  {result.analysis.product_b_name}: {result.analysis.unknown_ingredients_b.join(", ")}
                </p>
              )}
            </div>
          )}

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
    </div>
  );
}
