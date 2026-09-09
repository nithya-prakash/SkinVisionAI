import { ReactNode } from "react";

/** A neutral "nothing here yet" box -- used by the new History page's
 * per-section empty states, and reusable anywhere else a list can
 * legitimately be empty without it being an error.
 */
export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-neutral-300 bg-neutral-50 px-4 py-6 text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
      <p>{message}</p>
      {action}
    </div>
  );
}
