"use client";

import { useState } from "react";
import { Disclaimer, DISCLAIMER } from "@/components/Disclaimer";
import { ProductComparer } from "./ProductComparer";
import { SingleProductAnalyzer } from "./SingleProductAnalyzer";

type Mode = "analyze" | "compare";

export default function ComparePage() {
  const [mode, setMode] = useState<Mode>("analyze");

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === "analyze" ? "Ingredient Analysis" : "Product Comparison"}
      </h1>
      <p className="text-neutral-600 dark:text-neutral-300">
        {mode === "analyze"
          ? "Enter a product's ingredient list to see normalized ingredients, detected categories, and any documented compatibility notes."
          : "Compare two products' ingredients: shared and unique ingredients, shared active categories, and any documented compatibility notes between them."}
      </p>

      <div
        role="tablist"
        className="flex w-fit gap-1 rounded-full border border-neutral-200 p-1 dark:border-neutral-800"
      >
        <button
          role="tab"
          id="tab-analyze"
          aria-selected={mode === "analyze"}
          aria-controls="panel-analyze"
          onClick={() => setMode("analyze")}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
            mode === "analyze"
              ? "bg-neutral-900 text-white dark:bg-white dark:text-black"
              : "text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white"
          }`}
        >
          Analyze One Product
        </button>
        <button
          role="tab"
          id="tab-compare"
          aria-selected={mode === "compare"}
          aria-controls="panel-compare"
          onClick={() => setMode("compare")}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
            mode === "compare"
              ? "bg-neutral-900 text-white dark:bg-white dark:text-black"
              : "text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white"
          }`}
        >
          Compare Two Products
        </button>
      </div>

      {mode === "analyze" ? (
        <div role="tabpanel" id="panel-analyze" aria-labelledby="tab-analyze">
          <SingleProductAnalyzer />
        </div>
      ) : (
        <div role="tabpanel" id="panel-compare" aria-labelledby="tab-compare">
          <ProductComparer />
        </div>
      )}

      <Disclaimer className="mt-auto" text={DISCLAIMER} />
    </main>
  );
}
