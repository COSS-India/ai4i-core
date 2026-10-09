/**
 * True only when the server explicitly rejected the credentials (401).
 *
 * Network errors, timeouts and 5xx (e.g. auth-service restarting during a
 * deploy) must not end the session — the stored tokens are still valid and
 * the next request after recovery will succeed.
 *
 * 403 is deliberately excluded: APISIX forward-auth returns 403 when it
 * cannot reach /auth/validate, so a 403 can mean "auth-service is down".
 * Real 403 sign-outs (USER_INACTIVE / TENANT_*) are handled earlier by
 * responseIndicatesTenantSuspendedOrInactive.
 */
export function isAuthRejection(error: unknown): boolean {
  const err = error as any;
  const status = err?.status ?? err?.response?.status;
  return status === 401;
}
