/**
 * Thin API client. No skincare/business logic lives here or in any other
 * frontend file -- every meaningful decision (image quality scoring,
 * ingredient compatibility, routine analysis, product comparison,
 * recommendations) is computed by the backend. This file only calls the
 * API and types its responses; it never recomputes or second-guesses them.
 *
 * Endpoints are added as the backend implements them.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8010";

export interface HealthResponse {
  status: string;
  app_name: string;
  environment: string;
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status}`);
  }
  return res.json();
}

// --- Image upload / quality gate (Phase 2) ---

export type ImageQualityIssue =
  | "too_low_resolution"
  | "too_blurry"
  | "too_dark"
  | "overexposed"
  | "extreme_shadows"
  | "low_contrast"
  | "unsupported_format"
  | "unsupported_orientation"
  | "insufficient_skin_visibility";

export interface ImageQualityMetrics {
  width: number;
  height: number;
  aspect_ratio: number;
  file_size_bytes: number;
  blur_score: number;
  brightness_score: number;
  contrast_score: number;
  orientation: number | null;
}

export interface ImageQualityResult {
  score: number;
  is_acceptable: boolean;
  issues: ImageQualityIssue[];
  message: string | null;
  metrics: ImageQualityMetrics | null;
}

export interface ImageMetadata {
  id: string;
  session_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  width_px: number | null;
  height_px: number | null;
  content_hash: string;
  quality_result: ImageQualityResult | null;
  created_at: string;
}

export interface ImageUploadResponse {
  analysis_id: string;
  session_id: string;
  image: ImageMetadata;
  quality: ImageQualityResult;
}

export class UploadError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "UploadError";
    this.code = code;
  }
}

export async function uploadImage(
  file: File,
  sessionId?: string,
): Promise<ImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (sessionId) {
    formData.append("session_id", sessionId);
  }

  const res = await fetch(`${API_BASE_URL}/api/analysis/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    let code: string | undefined;
    let message = `Upload failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail?.message) {
        message = body.detail.message;
        code = body.detail.code;
      }
    } catch {
      // Response body wasn't JSON; fall back to the generic message above.
    }
    throw new UploadError(message, code);
  }

  return res.json();
}

// --- Visual analysis (Phase 3) ---

export type ObservationFeature =
  | "redness"
  | "dryness"
  | "visible_texture"
  | "shine_oiliness"
  | "uneven_tone"
  | "visible_spots_marks";

export type ObservationLevel = "minimal" | "mild" | "moderate" | "pronounced";

export type RegionSource = "detected_face" | "center_crop_fallback";

export interface VisualObservation {
  feature: ObservationFeature;
  level: ObservationLevel;
  score: number;
  confidence: number;
  method: string;
  note: string | null;
}

export interface VisualAnalysisResult {
  analysis_id: string;
  image_id: string;
  observations: VisualObservation[];
  region_used: RegionSource;
  limitations: string[];
  disclaimer: string;
  created_at: string;
}

export class VisualAnalysisRequestError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "VisualAnalysisRequestError";
    this.code = code;
  }
}

export async function runVisualAnalysis(
  analysisId: string,
): Promise<VisualAnalysisResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/analysis/${analysisId}/visual-analysis`,
    { method: "POST" },
  );

  if (!res.ok) {
    let code: string | undefined;
    let message = `Visual analysis failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail?.message) {
        message = body.detail.message;
        code = body.detail.code;
      }
    } catch {
      // Response body wasn't JSON; fall back to the generic message above.
    }
    throw new VisualAnalysisRequestError(message, code);
  }

  return res.json();
}

// --- Product ingredient analysis (Phase 4) ---

export type ProductCategory =
  | "cleanser"
  | "toner"
  | "serum"
  | "moisturizer"
  | "sunscreen"
  | "exfoliant"
  | "treatment"
  | "other";

export type IngredientCategory =
  | "retinoid"
  | "aha"
  | "bha"
  | "exfoliant"
  | "vitamin_c"
  | "antioxidant"
  | "humectant"
  | "occlusive"
  | "barrier_support"
  | "brightening"
  | "soothing_agent"
  | "sunscreen_filter"
  | "acne_treatment"
  | "preservative"
  | "fragrance"
  | "other";

export type RuleSeverity = "incompatibility" | "caution" | "informational" | "no_known_conflict";

export interface NormalizedIngredient {
  raw_text: string;
  normalized_name: string | null;
  matched: boolean;
  ambiguous: boolean;
  candidates: string[];
  categories: IngredientCategory[];
}

export interface IngredientInteraction {
  rule_id: string | null;
  ingredient_a: string;
  ingredient_b: string;
  severity: RuleSeverity;
  message: string;
  reason: string | null;
  source: string | null;
  source_url: string | null;
  last_verified: string | null;
}

export interface CompatibilityResult {
  ingredients: NormalizedIngredient[];
  interactions: IngredientInteraction[];
  unknown_ingredients: string[];
  limitations: string[];
  disclaimer: string;
}

export interface ProductAnalyzeResponse {
  product_id: string;
  session_id: string;
  name: string;
  category: ProductCategory | null;
  compatibility: CompatibilityResult;
}

export class ProductAnalysisError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "ProductAnalysisError";
    this.code = code;
  }
}

export async function analyzeProduct(input: {
  name: string;
  category?: ProductCategory;
  rawIngredientText: string;
  sessionId?: string;
}): Promise<ProductAnalyzeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/products/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      category: input.category ?? null,
      raw_ingredient_text: input.rawIngredientText,
      session_id: input.sessionId ?? null,
    }),
  });

  if (!res.ok) {
    let code: string | undefined;
    let message = `Ingredient analysis failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail?.message) {
        message = body.detail.message;
        code = body.detail.code;
      } else if (typeof body?.detail === "string") {
        message = body.detail;
      }
    } catch {
      // Response body wasn't JSON; fall back to the generic message above.
    }
    throw new ProductAnalysisError(message, code);
  }

  return res.json();
}

// --- Product comparison (Phase 5) ---

export interface ProductCompareItem {
  name: string;
  category?: ProductCategory;
  rawIngredientText: string;
}

export interface ProductComparisonResult {
  product_a_name: string;
  product_b_name: string;
  shared_ingredients: string[];
  only_in_a: string[];
  only_in_b: string[];
  shared_categories: IngredientCategory[];
  interactions: IngredientInteraction[];
  unknown_ingredients_a: string[];
  unknown_ingredients_b: string[];
  limitations: string[];
  disclaimer: string;
  /** Set only when the request had persist=true (Phase 8). */
  id?: string | null;
}

export async function compareProducts(
  productA: ProductCompareItem,
  productB: ProductCompareItem,
): Promise<ProductComparisonResult> {
  const res = await fetch(`${API_BASE_URL}/api/products/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      product_a: {
        name: productA.name,
        category: productA.category ?? null,
        raw_ingredient_text: productA.rawIngredientText,
      },
      product_b: {
        name: productB.name,
        category: productB.category ?? null,
        raw_ingredient_text: productB.rawIngredientText,
      },
    }),
  });

  if (!res.ok) {
    let code: string | undefined;
    let message = `Comparison failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail?.message) {
        message = body.detail.message;
        code = body.detail.code;
      }
    } catch {
      // Response body wasn't JSON; fall back to the generic message above.
    }
    throw new ProductAnalysisError(message, code);
  }

  return res.json();
}

// --- Routine analysis (Phase 5) ---

export type TimeOfDayPreference = "AM" | "PM" | "AM_AND_PM" | "unspecified";

export interface RoutineProductInput {
  productName: string;
  rawIngredients: string;
  category?: ProductCategory;
  intendedUse?: string;
  timeOfDay?: TimeOfDayPreference;
}

export interface RoutineProductAnalysis {
  product_name: string;
  category: ProductCategory | null;
  time_of_day: TimeOfDayPreference;
  normalized_ingredients: NormalizedIngredient[];
}

export interface OverlappingActive {
  ingredient: string;
  categories: IngredientCategory[];
  products: string[];
  count: number;
  message: string;
  reason: string | null;
  source: string | null;
  source_url: string | null;
  last_verified: string | null;
}

export interface RoutineInteraction extends IngredientInteraction {
  products: string[];
}

export interface ScheduledStep {
  product_name: string;
  category: ProductCategory;
  step_order: number;
}

export interface UnscheduledProduct {
  product_name: string;
  reason: string;
}

export interface RoutineAnalysisResult {
  products: RoutineProductAnalysis[];
  overlapping_actives: OverlappingActive[];
  interactions: RoutineInteraction[];
  suggested_am: ScheduledStep[];
  suggested_pm: ScheduledStep[];
  unscheduled_products: UnscheduledProduct[];
  limitations: string[];
  disclaimer: string;
  /** Set only when the request had persist=true (Phase 8). */
  id?: string | null;
}

export async function analyzeRoutine(
  products: RoutineProductInput[],
): Promise<RoutineAnalysisResult> {
  const res = await fetch(`${API_BASE_URL}/api/routine/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      products: products.map((p) => ({
        product_name: p.productName,
        raw_ingredients: p.rawIngredients,
        category: p.category ?? null,
        intended_use: p.intendedUse ?? null,
        time_of_day: p.timeOfDay ?? "unspecified",
      })),
    }),
  });

  if (!res.ok) {
    let code: string | undefined;
    let message = `Routine analysis failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail?.message) {
        message = body.detail.message;
        code = body.detail.code;
      }
    } catch {
      // Response body wasn't JSON; fall back to the generic message above.
    }
    throw new ProductAnalysisError(message, code);
  }

  return res.json();
}

// --- LLM explanations (Phase 6) ---
//
// These endpoints re-run the same deterministic analysis as the endpoints
// above and additionally attach an AI-generated narrative explanation.
// The deterministic `analysis` is always present; `explanation` is only
// present when the LLM call succeeded and passed anti-hallucination
// validation on the backend -- explanation_status/explanation_error tell
// the UI which case it's in. The LLM never supplies severity, source, or
// source_url on any item; those always come from the deterministic result.

export type ExplanationStatus = "available" | "unavailable";

export interface InteractionExplanation {
  rule_id: string | null;
  ingredient_a: string;
  ingredient_b: string;
  severity: RuleSeverity;
  message: string;
  source: string | null;
  source_url: string | null;
  explanation: string;
}

export interface OverlapExplanation {
  ingredient: string;
  products: string[];
  message: string;
  source: string | null;
  source_url: string | null;
  explanation: string;
}

export interface Explanation {
  summary: string;
  key_points: string[];
  interactions_explained: InteractionExplanation[];
  overlap_explained: OverlapExplanation[];
  routine_notes: string[];
  limitations: string[];
  disclaimer: string;
}

interface ExplanationEnvelope {
  explanation: Explanation | null;
  explanation_status: ExplanationStatus;
  explanation_error: string | null;
}

export interface ProductExplanationResponse extends ExplanationEnvelope {
  analysis: CompatibilityResult;
}

export interface ComparisonExplanationResponse extends ExplanationEnvelope {
  analysis: ProductComparisonResult;
}

export interface RoutineExplanationResponse extends ExplanationEnvelope {
  analysis: RoutineAnalysisResult;
}

async function parseErrorBody(res: Response, fallback: string): Promise<ProductAnalysisError> {
  let code: string | undefined;
  let message = fallback;
  try {
    const body = await res.json();
    if (body?.detail?.message) {
      message = body.detail.message;
      code = body.detail.code;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    }
  } catch {
    // Response body wasn't JSON; fall back to the generic message above.
  }
  return new ProductAnalysisError(message, code);
}

export async function explainProduct(input: {
  name: string;
  category?: ProductCategory;
  rawIngredientText: string;
  sessionId?: string;
}): Promise<ProductExplanationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/explanations/product`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      category: input.category ?? null,
      raw_ingredient_text: input.rawIngredientText,
      session_id: input.sessionId ?? null,
    }),
  });
  // Note: /api/explanations/product re-runs analysis statelessly and has
  // no persist option -- use /api/products/analyze directly (persisted
  // by default since Phase 4) if a retrievable product id is needed.

  if (!res.ok) {
    throw await parseErrorBody(res, `Explanation request failed (${res.status}).`);
  }
  return res.json();
}

export async function explainComparison(
  productA: ProductCompareItem,
  productB: ProductCompareItem,
  options?: { sessionId?: string; persist?: boolean },
): Promise<ComparisonExplanationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/explanations/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      product_a: {
        name: productA.name,
        category: productA.category ?? null,
        raw_ingredient_text: productA.rawIngredientText,
      },
      product_b: {
        name: productB.name,
        category: productB.category ?? null,
        raw_ingredient_text: productB.rawIngredientText,
      },
      session_id: options?.sessionId ?? null,
      persist: options?.persist ?? false,
    }),
  });

  if (!res.ok) {
    throw await parseErrorBody(res, `Explanation request failed (${res.status}).`);
  }
  return res.json();
}

export async function explainRoutine(
  products: RoutineProductInput[],
  options?: { sessionId?: string; persist?: boolean },
): Promise<RoutineExplanationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/explanations/routine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      products: products.map((p) => ({
        product_name: p.productName,
        raw_ingredients: p.rawIngredients,
        category: p.category ?? null,
        intended_use: p.intendedUse ?? null,
        time_of_day: p.timeOfDay ?? "unspecified",
      })),
      session_id: options?.sessionId ?? null,
      persist: options?.persist ?? false,
    }),
  });

  if (!res.ok) {
    throw await parseErrorBody(res, `Explanation request failed (${res.status}).`);
  }
  return res.json();
}

// --- Agent chat (Phase 7) ---
//
// The agent decides which deterministic tool(s) to call and explains the
// result -- it never computes a skincare fact itself. This client only
// sends the user's message and renders the structured response,
// including the tool trace, exactly as the backend returns it.

export type AgentStatus =
  | "success"
  | "tool_error"
  | "llm_unavailable"
  | "validation_error"
  | "max_tool_calls";

export interface ToolCallTraceEntry {
  tool_name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  call_index: number;
  success: boolean;
  error: string | null;
}

export interface AgentCitation {
  source: string;
  source_url: string | null;
}

export interface AgentResponse {
  answer: string;
  tool_trace: ToolCallTraceEntry[];
  citations: AgentCitation[];
  limitations: string[];
  disclaimer: string;
  status: AgentStatus;
  chat_session_id: string | null;
  message_id: string | null;
}

export async function sendAgentChatMessage(input: {
  message: string;
  chatSessionId?: string;
  sessionId?: string;
  context?: Record<string, unknown>;
}): Promise<AgentResponse> {
  const res = await fetch(`${API_BASE_URL}/api/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: input.message,
      chat_session_id: input.chatSessionId ?? null,
      session_id: input.sessionId ?? null,
      context: input.context ?? null,
    }),
  });

  if (!res.ok) {
    throw await parseErrorBody(res, `Agent chat request failed (${res.status}).`);
  }
  return res.json();
}

// --- Application sessions, analysis retrieval, chat history (Phase 8) ---
//
// A session id is a plain, non-secret UUID -- see lib/session.ts for the
// client-side localStorage helper that keeps it stable across a page
// refresh. These functions only read/create already-computed backend
// state; none of them compute a skincare fact.

export interface SessionRead {
  id: string;
  created_at: string;
}

export async function createSession(): Promise<SessionRead> {
  const res = await fetch(`${API_BASE_URL}/api/sessions`, { method: "POST" });
  if (!res.ok) {
    throw await parseErrorBody(res, `Session creation failed (${res.status}).`);
  }
  return res.json();
}

export type AnalysisClientStatus =
  | "quality_rejected"
  | "ready_for_visual_analysis"
  | "analyzing"
  | "completed"
  | "failed";

export interface AnalysisDetailResponse {
  id: string;
  session_id: string;
  status: AnalysisClientStatus;
  image: ImageMetadata;
  visual_analysis: VisualAnalysisResult | null;
  disclaimer: string;
  created_at: string;
  updated_at: string;
}

export class AnalysisNotFoundError extends Error {}

export async function getAnalysis(analysisId: string): Promise<AnalysisDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/api/analysis/${analysisId}`, { cache: "no-store" });
  if (res.status === 404) {
    throw new AnalysisNotFoundError("No analysis exists with that id.");
  }
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching analysis failed (${res.status}).`);
  }
  return res.json();
}

export interface ChatSessionRead {
  id: string;
  session_id: string;
  skin_analysis_id: string | null;
  product_id: string | null;
  routine_analysis_id: string | null;
  comparison_id: string | null;
  created_at: string;
  updated_at: string;
}

export async function getChatSession(chatSessionId: string): Promise<ChatSessionRead> {
  const res = await fetch(`${API_BASE_URL}/api/chat/sessions/${chatSessionId}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching chat session failed (${res.status}).`);
  }
  return res.json();
}

export interface ChatMessageRead {
  id: string;
  chat_session_id: string;
  role: string;
  content: string;
  tool_trace: ToolCallTraceEntry[];
  created_at: string;
}

export interface ChatMessagesResponse {
  chat_session_id: string;
  messages: ChatMessageRead[];
}

export async function getChatMessages(chatSessionId: string): Promise<ChatMessagesResponse> {
  const res = await fetch(`${API_BASE_URL}/api/chat/sessions/${chatSessionId}/messages`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching chat history failed (${res.status}).`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Session history lists (Phase 9) -- each mirrors an existing GET
// /api/sessions/{id}/... endpoint added across Phase 8/9. All are read-only
// summaries of already-persisted state; none compute a skincare fact.

export interface SessionAnalysisSummary {
  id: string;
  status: AnalysisClientStatus;
  created_at: string;
}

export interface SessionAnalysesResponse {
  session_id: string;
  analyses: SessionAnalysisSummary[];
}

export async function listSessionAnalyses(sessionId: string): Promise<SessionAnalysesResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/analyses`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching session analyses failed (${res.status}).`);
  }
  return res.json();
}

export interface SessionChatSummary {
  id: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionChatsResponse {
  session_id: string;
  chats: SessionChatSummary[];
}

export async function listSessionChats(sessionId: string): Promise<SessionChatsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/chats`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching session chats failed (${res.status}).`);
  }
  return res.json();
}

export interface SessionProductSummary {
  id: string;
  name: string;
  category: string | null;
  interaction_count: number;
  unknown_ingredient_count: number;
  created_at: string;
}

export interface SessionProductsResponse {
  session_id: string;
  products: SessionProductSummary[];
}

export async function listSessionProducts(sessionId: string): Promise<SessionProductsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/products`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching session products failed (${res.status}).`);
  }
  return res.json();
}

export interface SessionRoutineAnalysisSummary {
  id: string;
  product_count: number;
  interaction_count: number;
  created_at: string;
}

export interface SessionRoutineAnalysesResponse {
  session_id: string;
  routine_analyses: SessionRoutineAnalysisSummary[];
}

export async function listSessionRoutineAnalyses(
  sessionId: string,
): Promise<SessionRoutineAnalysesResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/routine-analyses`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching session routine analyses failed (${res.status}).`);
  }
  return res.json();
}

export interface SessionComparisonSummary {
  id: string;
  product_a_name: string;
  product_b_name: string;
  interaction_count: number;
  created_at: string;
}

export interface SessionComparisonsResponse {
  session_id: string;
  comparisons: SessionComparisonSummary[];
}

export async function listSessionComparisons(
  sessionId: string,
): Promise<SessionComparisonsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/comparisons`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseErrorBody(res, `Fetching session comparisons failed (${res.status}).`);
  }
  return res.json();
}
