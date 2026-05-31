/**
 * Auth-service v2 JSON shape: `{ success, data }`. Returns inner `data` when present.
 */
export function unwrapAuthV2Payload(raw: unknown): unknown {
  if (raw && typeof raw === 'object' && 'success' in raw && 'data' in raw) {
    return (raw as { data: unknown }).data;
  }
  return raw;
}

/**
 * Platform / try-it responses that nest the payload under `data`.
 */
export function unwrapPlatformDataEnvelope(raw: unknown): unknown {
  if (raw && typeof raw === 'object' && 'data' in raw) {
    const data = (raw as { data: unknown }).data;
    if (data !== undefined) return data;
  }
  return raw;
}
