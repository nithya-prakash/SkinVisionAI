import { AgentStatus, RuleSeverity } from "@/lib/api";

export type BadgeTone = "neutral" | "info" | "warning" | "danger";

const TONE_STYLES: Record<BadgeTone, string> = {
  neutral: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300",
  info: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  danger: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

/** Generic pill badge. Every page-specific meaning (a severity, an agent
 * status) maps to one of these four tones via the helpers below, rather
 * than each page hand-rolling its own badge markup and color map.
 */
export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: BadgeTone }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${TONE_STYLES[tone]}`}>
      {label}
    </span>
  );
}

const SEVERITY_LABELS: Record<RuleSeverity, string> = {
  incompatibility: "Incompatibility",
  caution: "Caution",
  informational: "Informational",
  no_known_conflict: "No known conflict",
};

const SEVERITY_TONES: Record<RuleSeverity, BadgeTone> = {
  incompatibility: "danger",
  caution: "warning",
  informational: "info",
  no_known_conflict: "neutral",
};

/** The one place a `RuleSeverity` maps to a label/color -- previously
 * duplicated (with a drifted copy in routine/page.tsx) across 3 files.
 */
export function SeverityBadge({ severity }: { severity: RuleSeverity }) {
  return <StatusBadge label={SEVERITY_LABELS[severity]} tone={SEVERITY_TONES[severity]} />;
}

const AGENT_STATUS_LABELS: Partial<Record<AgentStatus, string>> = {
  tool_error: "A tool call failed",
  llm_unavailable: "AI assistant unavailable",
  validation_error: "Answer did not pass validation",
  max_tool_calls: "Reached the step limit for this request",
};

const AGENT_STATUS_TONES: Partial<Record<AgentStatus, BadgeTone>> = {
  tool_error: "warning",
  llm_unavailable: "danger",
  validation_error: "warning",
  max_tool_calls: "neutral",
};

/** Renders nothing for `"success"` (the normal case, no badge needed).
 * Each non-success status gets its own tone rather than one uniform
 * amber badge for every failure kind.
 */
export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  if (status === "success") return null;
  return (
    <StatusBadge
      label={AGENT_STATUS_LABELS[status] ?? status}
      tone={AGENT_STATUS_TONES[status] ?? "warning"}
    />
  );
}
