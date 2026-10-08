/**
 * True only when the server explicitly rejected the credentials (401/403).
 *
 * Network errors, timeouts and 5xx (e.g. auth-service restarting during a
 * deploy) carry no such status and must not end the session — the stored
 * tokens are still valid and the next request after recovery will succeed.
 */
export function isAuthRejection(error: unknown): boolean {
  const err = error as any;
  const status = err?.status ?? err?.response?.status;
  return status === 401 || status === 403;
}
