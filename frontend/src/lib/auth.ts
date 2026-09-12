/**
 * Authentication client (release-hardening follow-up). The session is
 * an httpOnly cookie set by the backend -- this file never reads,
 * stores, or attaches a token itself; every call just goes through
 * lib/api.ts's apiFetch, which sends the cookie automatically via
 * `credentials: "include"`.
 */
import { API_BASE_URL } from "./api";

export interface CurrentUser {
  id: string;
  email: string;
  session_id: string;
  created_at: string;
}

export class AuthError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "AuthError";
    this.code = code;
  }
}

async function parseAuthError(res: Response, fallback: string): Promise<AuthError> {
  let message = fallback;
  let code: string | undefined;
  try {
    const body = await res.json();
    if (body?.detail?.message) {
      message = body.detail.message;
      code = body.detail.code;
    }
  } catch {
    // Response body wasn't JSON; fall back to the generic message above.
  }
  return new AuthError(message, code);
}

export async function register(email: string, password: string): Promise<CurrentUser> {
  const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw await parseAuthError(res, `Registration failed (${res.status}).`);
  }
  return res.json();
}

export async function login(email: string, password: string): Promise<CurrentUser> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw await parseAuthError(res, `Sign in failed (${res.status}).`);
  }
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

/** Returns the signed-in user, or `null` if no one is signed in. Never
 * throws for the "not signed in" case (401) -- that's an expected,
 * common state for this call, not an error.
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) {
    return null;
  }
  if (!res.ok) {
    throw await parseAuthError(res, `Could not check sign-in status (${res.status}).`);
  }
  return res.json();
}
