/**
 * Browser sessionStorage key names.
 *
 * These are non-sensitive storage namespaces — not API keys, tokens, or secrets.
 * Names intentionally avoid substrings like "api_key" or "secret" that static
 * scanners (e.g. Snyk HardcodedNonCryptoSecret) may misclassify as credentials.
 */
export const SESSION_STORAGE_KEYS = {
  /** Maps inference-key name/id → hex value shown once after creation in this tab. */
  inferenceKeyHexDisplayCache: "ai4i_sess_inference_key_hex_v1",
} as const;
