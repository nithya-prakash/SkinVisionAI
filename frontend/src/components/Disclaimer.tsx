/** The base disclaimer sentence, identical to every backend response's
 * `disclaimer` field -- exported so pages with no visual-analysis
 * involvement (`/compare`, `/routine`, `/chat`) can pass it as `text`
 * even before a backend response exists yet, instead of duplicating the
 * literal string.
 */
export const DISCLAIMER =
  "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.";

const VISUAL_ANALYSIS_NOTE =
  "These observations are visual estimates and may be affected by lighting, camera quality, and image conditions. If you have a medical concern, please consult a qualified healthcare professional.";

/**
 * `text`, when given, overrides the default wording -- pass the actual
 * `disclaimer` string a backend response already returned (every
 * endpoint's `disclaimer` field is the same base sentence) rather than
 * always showing the visual-analysis-specific second sentence below,
 * which is only accurate on `/results/[id]`. Omit `text` to keep that
 * page's existing, correct wording unchanged.
 */
export function Disclaimer({ className = "", text }: { className?: string; text?: string }) {
  return (
    <p className={`text-sm text-neutral-500 dark:text-neutral-400 ${className}`}>
      {text ?? `${DISCLAIMER} ${VISUAL_ANALYSIS_NOTE}`}
    </p>
  );
}
