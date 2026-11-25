/**
 * Span attributes as shown in the Trace details popup.
 *
 * The inference service stores the request's `metadata` object as one span
 * attribute, `metadata_kv`: a list of "key=value" strings, so every tenant key
 * shares one OpenSearch field. Display it the way the caller sent it. Keys
 * can't contain "=" (rejected at validation), so the key ends at the first one.
 */
export function toDisplayAttributes(
  attrs: Record<string, unknown>,
): Record<string, unknown> {
  const kv = attrs.metadata_kv;
  if (!Array.isArray(kv) || "metadata" in attrs) return attrs;
  const metadata: Record<string, string> = {};
  for (const entry of kv) {
    const text = String(entry);
    const sep = text.indexOf("=");
    if (sep === -1) return attrs;
    metadata[text.slice(0, sep)] = text.slice(sep + 1);
  }
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "metadata_kv") out.metadata = metadata;
    else out[key] = value;
  }
  return out;
}

/**
 * True when the span ran on the fallback model. The inference service sets
 * `is_fallback` on its `model` and `ai-inference` spans; accept the string
 * form too in case the attribute was stored as text.
 */
export function isFallbackSpan(attrs: Record<string, unknown> | undefined): boolean {
  const flag = attrs?.is_fallback;
  return flag === true || String(flag).toLowerCase() === "true";
}
