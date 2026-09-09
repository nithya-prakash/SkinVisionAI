/**
 * Client-side application-session persistence (Phase 8).
 *
 * A session id is a plain, non-secret UUID -- never a credential. It is
 * stored in localStorage purely so a page refresh doesn't lose
 * continuity (which analyses/chats belong together); it grants no
 * capability beyond what any other UUID-addressable resource in this
 * app already exposes (see docs/persistence.md's security section).
 *
 * Server-side session creation/lookup is unaffected by this file --
 * every backend call that accepts an optional session_id still works
 * fine without one (it just creates a fresh anonymous session), this
 * module only makes the frontend consistently reuse the same one.
 */

import { createSession } from "./api";

const STORAGE_KEY = "skinvision_session_id";

/** Read the stored session id, if any. Never throws. */
export function getStoredSessionId(): string | undefined {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Persist a session id returned by the backend. Never throws. */
export function setStoredSessionId(sessionId: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, sessionId);
  } catch {
    // Private browsing / storage disabled -- the app still works, just
    // without cross-refresh continuity for this viewer.
  }
}

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
    // See getStoredSessionId.
  }
}

/**
 * The stored session id if one exists; otherwise creates one via the
 * backend and stores it. Every page that wants cross-refresh continuity
 * calls this once (e.g. in a mount effect) rather than reading
 * localStorage directly.
 */
export async function getOrCreateAppSession(): Promise<string> {
  const existing = getStoredSessionId();
  if (existing) return existing;

  const session = await createSession();
  setStoredSessionId(session.id);
  return session.id;
}
