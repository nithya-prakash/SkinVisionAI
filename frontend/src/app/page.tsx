import Link from "next/link";
import { Disclaimer } from "@/components/Disclaimer";

const CAPABILITIES = [
  {
    title: "Visual analysis",
    description:
      "Upload a photo. A deterministic computer-vision pipeline (OpenCV) reports non-diagnostic visible characteristics — redness, texture, tone — with confidence and limitations, never a condition label.",
    href: "/analyze",
    cta: "Analyze Skin",
  },
  {
    title: "Ingredient & routine analysis",
    description:
      "Enter ingredient lists or a full routine. A sourced, versioned rule engine checks compatibility and overlap — the LLM never decides a severity or invents an interaction.",
    href: "/compare",
    cta: "Analyze Products",
  },
  {
    title: "AI assistant",
    description:
      "Ask a question. A bounded tool-calling agent picks a deterministic tool, reads its result, and explains it — every answer is validated against the tool trace before it reaches you.",
    href: "/chat",
    cta: "Ask AI Assistant",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-10 px-6 py-16">
      <div className="flex flex-col gap-4">
        <h1 className="text-4xl font-semibold tracking-tight">SkinVision AI</h1>
        <p className="text-lg text-neutral-600 dark:text-neutral-300">
          A portfolio-grade skincare analysis project combining computer
          vision, a deterministic ingredient rule engine, and a bounded,
          validated LLM explanation layer. The model explains results; it
          never decides them.
        </p>
      </div>

      <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <strong>Educational only, not medical diagnosis.</strong> SkinVision
        AI describes visible skincare-related characteristics and documented
        ingredient interactions &mdash; it does not diagnose medical
        conditions, guarantee outcomes, or replace professional advice. This
        project uses synthetic and demo data.
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {CAPABILITIES.map((capability) => (
          <div
            key={capability.href}
            className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-5 dark:border-neutral-800"
          >
            <h2 className="font-medium">{capability.title}</h2>
            <p className="flex-1 text-sm text-neutral-600 dark:text-neutral-300">
              {capability.description}
            </p>
            <Link
              href={capability.href}
              className="self-start rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
            >
              {capability.cta}
            </Link>
          </div>
        ))}
      </div>

      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Everything you do is tied to an anonymous, local session &mdash; no
        account required.{" "}
        <Link href="/history" className="underline underline-offset-2">
          View your session history
        </Link>
        .
      </p>

      <Disclaimer />
    </main>
  );
}
