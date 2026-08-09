// Anonymous session ID utility for rate limiting
// Generates and stores a unique session ID for anonymous users
// Used by the backend to track rate limits for try-it feature
import { getStoredAccessToken } from './tokenStorage';
import { generateUUID } from './uuid';

/**
 * Get or create anonymous session ID
 * This ID is used for rate limiting on the backend
 * @returns Anonymous session ID
 */
export function getAnonymousSessionId(): string {
  const key = 'anonymous_session_id';

  if (typeof window === 'undefined') {
    // Server-side: generate temporary ID
    return generateUUID();
  }

  try {
    // Check if we already have a session ID
    let sessionId = sessionStorage.getItem(key);

    if (!sessionId) {
      // Generate new session ID
      sessionId = generateUUID();
      sessionStorage.setItem(key, sessionId);
    }

    return sessionId;
  } catch (e) {
    // If sessionStorage is not available, generate temporary ID
    console.warn('Failed to access sessionStorage for anonymous session ID:', e);
    return generateUUID();
  }
}

/**
 * Clear anonymous session ID
 * Useful when user logs in or logs out
 */
export function clearAnonymousSessionId(): void {
  const key = 'anonymous_session_id';

  if (typeof window === 'undefined') return;

  try {
    sessionStorage.removeItem(key);
  } catch (e) {
    console.warn('Failed to clear anonymous session ID:', e);
  }
}

/**
 * Check if current user is anonymous (not authenticated)
 * @returns boolean indicating if user is anonymous
 */
/**
 * True when the browser should use public try-it APIs (no JWT).
 * A leftover access token without a stored user profile is treated as anonymous
 * so stale sessions do not hit authenticated routes and get 401.
 */
export function isAnonymousUser(): boolean {
  if (typeof window === 'undefined') return true;

  try {
    const hasAccessToken = getStoredAccessToken();
    if (!hasAccessToken) return true;
    const hasStoredUser =
      typeof sessionStorage !== 'undefined' && !!sessionStorage.getItem('user');
    return !hasStoredUser;
  } catch {
    return true;
  }
}
