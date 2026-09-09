import { AgentCitation, ToolCallTraceEntry } from "@/lib/api";

/**
 * A short, human-readable one-line summary of one tool call's result, for
 * the "How SkinVision AI reached this answer" trace display. Purely
 * presentational -- every fact it shows already came from the backend's
 * structured trace; this never computes or infers anything new.
 */
export function summarizeToolResult(entry: ToolCallTraceEntry): string {
  if (!entry.success) {
    return entry.error ?? "This tool call failed.";
  }
  const result = entry.result as Record<string, unknown> | null;
  if (!result) return "No result.";

  switch (entry.tool_name) {
    case "check_ingredient_compatibility":
    case "analyze_product": {
      const interactions = asArray(result.interactions);
      if (interactions.length === 0) return "No documented interactions found.";
      return interactions
        .map((i) => `${i.ingredient_a} + ${i.ingredient_b} → ${i.severity}`)
        .join("; ");
    }
    case "compare_products": {
      const shared = asStringArray(result.shared_ingredients);
      const interactions = asArray(result.interactions);
      const parts: string[] = [];
      parts.push(shared.length > 0 ? `Shared: ${shared.join(", ")}` : "No shared ingredients");
      if (interactions.length > 0) {
        parts.push(
          interactions.map((i) => `${i.ingredient_a} + ${i.ingredient_b} → ${i.severity}`).join("; "),
        );
      }
      return parts.join(". ");
    }
    case "analyze_routine": {
      const overlaps = asArray(result.overlapping_actives);
      const interactions = asArray(result.interactions);
      const parts: string[] = [];
      parts.push(
        overlaps.length > 0
          ? `${overlaps.length} overlapping active(s)`
          : "No overlapping actives",
      );
      if (interactions.length > 0) {
        parts.push(
          interactions.map((i) => `${i.ingredient_a} + ${i.ingredient_b} → ${i.severity}`).join("; "),
        );
      }
      return parts.join(". ");
    }
    case "get_ingredient_information": {
      const matched = result.matched === true;
      const name = typeof result.normalized_name === "string" ? result.normalized_name : null;
      const categories = asStringArray(result.categories);
      if (!matched) return "Not recognized in this system's rule set.";
      return categories.length > 0 ? `${name} (${categories.join(", ")})` : String(name);
    }
    default:
      return "Result received.";
  }
}

function asArray(value: unknown): Array<Record<string, string>> {
  return Array.isArray(value) ? (value as Array<Record<string, string>>) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

/**
 * Deduplicated citations found anywhere in a tool trace -- mirrors the
 * backend's own extraction (app.agent.agent._extract_citations) so a
 * message hydrated from chat history (which only carries its trace, not
 * a full live AgentResponse) renders identically to one just received.
 * Purely presentational: every fact here already came from the trace.
 */
export function citationsFromTrace(trace: ToolCallTraceEntry[]): AgentCitation[] {
  const seen = new Map<string, string | null>();
  function walk(value: unknown): void {
    if (Array.isArray(value)) {
      value.forEach(walk);
    } else if (value && typeof value === "object") {
      const obj = value as Record<string, unknown>;
      const source = obj.source;
      if (typeof source === "string" && source && !seen.has(source)) {
        const url = obj.source_url;
        seen.set(source, typeof url === "string" ? url : null);
      }
      Object.values(obj).forEach(walk);
    }
  }
  trace.forEach((entry) => entry.success && walk(entry.result));
  return Array.from(seen.entries()).map(([source, source_url]) => ({ source, source_url }));
}
