/**
 * Client-side session helpers (Phase 8; release-hardening follow-up
 * simplifies the session half of this file).
 *
 * A session is now the authenticated user's own, owned session (see
 * lib/auth.ts) -- not a client-generated anonymous identity worth
 * caching in localStorage. `getOrCreateAppSession()` keeps its existing
 * signature (every page below still calls it the same way) but now
 * simply asks the backend for "my session" each time, idempotently
 * (`POST /api/sessions` always returns the same row for a signed-in
 * user); the backend, not localStorage, is the source of truth for
 * which session is yours.
 *
 * Chat-session-id caching (below) is unrelated and unchanged: it's a
 * pure refresh-continuity nicety, not an access-control mechanism --
 * the backend checks chat-session ownership regardless of where the id
 * came from (see docs/persistence.md's Security section).
 */

import { createSession } from "./api";

const CHAT_STORAGE_KEY = "skinvision_chat_session_id";

export function getStoredChatSessionId(): string | undefined {
  try {
    return localStorage.getItem(CHAT_STORAGE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

export function setStoredChatSessionId(chatSessionId: string): void {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, chatSessionId);
  } catch {
    // Private browsing / storage disabled -- the app still works, just
    // without cross-refresh chat continuity for this viewer.
  }
}

/**
 * The signed-in user's own session id. Requires authentication --
 * callers should already have confirmed a user is signed in (see each
 * page's auth-gate check) before calling this.
 */
export async function getOrCreateAppSession(): Promise<string> {
  const session = await createSession();
  return session.id;
}
