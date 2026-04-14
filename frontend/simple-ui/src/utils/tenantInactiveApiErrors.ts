/**
 * Detect API responses that mean the tenant or tenant-user is no longer allowed
 * to use the product (suspended, deactivated, removed, etc.). Call sites should
 * end the frontend session when this returns true.
 */

const LIFECYCLE_ERROR_CODES = new Set([
  'TENANT_INACTIVE',
  'TENANT_USER_INACTIVE',
  'TENANT_SUSPENDED',
  'TENANT_NOT_FOUND',
  'USER_INACTIVE',
  /** Auth validate: user record gone while JWT still present */
  'USER_NOT_FOUND',
]);

/** Message fragments from platform / gateway / telemetry (lowercase). */
const LIFECYCLE_MESSAGE_MARKERS = [
  'tenant not found or inactive',
  'tenant access is restricted',
  'your account access has been suspended',
  'access has been suspended',
  'tenant is suspended',
  'tenant is deactivated',
  'tenant was deactivated',
  'tenant status is suspended',
  'tenant status is deactivated',
  'tenant status is pending',
  'user is suspended',
  'user is deactivated',
];

function visitPayload(
  node: unknown,
  codes: Set<string>,
  texts: string[],
  depth: number
): void {
  if (node == null || depth > 12) return;
  if (typeof node === 'string') {
    texts.push(node);
    return;
  }
  if (typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const item of node) visitPayload(item, codes, texts, depth + 1);
    return;
  }
  const rec = node as Record<string, unknown>;
  for (const key of ['error', 'code']) {
    if (rec[key] != null && typeof rec[key] !== 'object') {
      codes.add(String(rec[key]).trim().toUpperCase());
    }
  }
  for (const key of ['message', 'msg', 'description']) {
    if (typeof rec[key] === 'string') texts.push(rec[key]);
  }
  if (rec.detail !== undefined) visitPayload(rec.detail, codes, texts, depth + 1);
}

function lifecycleCodesMatch(codes: Set<string>): boolean {
  for (const c of codes) {
    if (LIFECYCLE_ERROR_CODES.has(c)) return true;
    if (
      c.includes('TENANT') &&
      (c.includes('INACTIVE') || c.includes('SUSPENDED') || c.includes('NOT_FOUND'))
    ) {
      return true;
    }
    if (c === 'USER_INACTIVE' || c.includes('USER_INACTIVE')) return true;
  }
  return false;
}

function lifecycleMessagesMatch(textBlob: string): boolean {
  const lower = textBlob.toLowerCase();
  return LIFECYCLE_MESSAGE_MARKERS.some((m) => lower.includes(m));
}

/**
 * @param status HTTP status from axios (401 and 403 are used for these states today)
 */
export function responseIndicatesTenantSuspendedOrInactive(
  status: number | undefined,
  data: unknown
): boolean {
  if (status !== 401 && status !== 403) return false;
  const codes = new Set<string>();
  const texts: string[] = [];
  visitPayload(data, codes, texts, 0);
  if (lifecycleCodesMatch(codes)) return true;
  return lifecycleMessagesMatch(texts.join('\n'));
}
