/** A red-bordered `role="alert"` box with an optional retry action --
 * previously hand-rolled per page (ResultsClient, chat, etc.) with
 * subtly different markup each time.
 */
export function ErrorState({
  message,
  onRetry,
  retryLabel = "Retry",
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
    >
      <p>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-full border border-red-400 px-4 py-1.5 text-sm font-medium hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-900"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
