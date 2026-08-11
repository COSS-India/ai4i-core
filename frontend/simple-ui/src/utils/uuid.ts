// Shared UUID helper.
// crypto.randomUUID is exposed only in secure contexts (HTTPS, or localhost),
// so it is undefined when the portal is served over plain HTTP. Call this
// helper instead of crypto.randomUUID directly so both deployments work.

/**
 * Generate a random UUID v4
 */
export function generateUUID(): string {
  // Use crypto.randomUUID if available (secure contexts only)
  if (typeof window !== 'undefined' && window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }

  // Fallback to manual UUID generation using crypto.getRandomValues(), which
  // is available in insecure contexts as well
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant bits
  return Array.from(bytes).map((b, i) =>
    [4, 6, 8, 10].includes(i) ? `-${b.toString(16).padStart(2, '0')}` : b.toString(16).padStart(2, '0')
  ).join('');
}
