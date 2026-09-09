/** The "Limitations" box, byte-for-byte duplicated across
 * ResultsClient/SingleProductAnalyzer/ProductComparer/routine before
 * Phase 9 -- every list already comes straight from a backend response,
 * this only renders it consistently.
 */
export function LimitationList({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) return null;
  return (
    <div className="rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
      <p className="mb-1 font-medium">Limitations</p>
      <ul className="list-disc pl-5">
        {limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </div>
  );
}
