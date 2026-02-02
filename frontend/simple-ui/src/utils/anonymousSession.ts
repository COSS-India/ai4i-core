// Anonymous session ID utility for rate limiting
// Generates and stores a unique session ID for anonymous users
// Used by the backend to track rate limits for try-it feature

/**
 * Generate a random UUID v4
 */
function generateUUID(): string {
  // Use crypto.randomUUID if available (modern browsers)
  if (typeof window !== 'undefined' && window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  
  // Fallback to manual UUID generation
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

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
export function isAnonymousUser(): boolean {
  if (typeof window === 'undefined') return true;
  
  try {
    // Check if user has access token
    const hasAccessToken = 
      localStorage.getItem('access_token') || 
      sessionStorage.getItem('access_token');
    
    return !hasAccessToken;
  } catch (e) {
    return true;
  }
}

