// Anonymous session ID utility for rate limiting
// Generates and stores a unique session ID for anonymous users
// Used by the backend to track rate limits for try-it feature
import { getStoredAccessToken } from './tokenStorage';
import { SESSION_STORAGE_KEYS } from '../constants/storage';

/**
 * Generate a random UUID v4
 */
function generateUUID(): string {
  // Use crypto.randomUUID if available (modern browsers)
  if (typeof window !== 'undefined' && window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }

  // Fallback to manual UUID generation using crypto.getRandomValues()
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant bits
  return Array.from(bytes).map((b, i) =>
    [4, 6, 8, 10].includes(i) ? `-${b.toString(16).padStart(2, '0')}` : b.toString(16).padStart(2, '0')
  ).join('');
}

/**
 * Get or create anonymous session ID
 * This ID is used for rate limiting on the backend
 * @returns Anonymous session ID
 */
export function getAnonymousSessionId(): string {
  const key = SESSION_STORAGE_KEYS.ANONYMOUS_SESSION_ID;

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
  const key = SESSION_STORAGE_KEYS.ANONYMOUS_SESSION_ID;

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
      typeof sessionStorage !== 'undefined' &&
      !!sessionStorage.getItem(SESSION_STORAGE_KEYS.USER);
    return !hasStoredUser;
  } catch {
    return true;
  }
}
