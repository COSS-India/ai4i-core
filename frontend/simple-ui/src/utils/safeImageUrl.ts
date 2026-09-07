/** Raster image MIME types allowed in data: URLs (SVG excluded — scriptable content). */
const ALLOWED_RASTER_DATA_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/gif",
  "image/webp",
]);

const DANGEROUS_SCHEME_RE = /^(?:javascript|vbscript|file|about):/i;

function parseDataImageMimeType(url: string): string | null {
  const match = url.match(/^data:(image\/[^;,]+)/i);
  return match ? match[1].toLowerCase() : null;
}

function decodeForSchemeCheck(url: string): string {
  try {
    return decodeURI(url);
  } catch {
    return url;
  }
}

function hasDangerousScheme(url: string): boolean {
  const normalized = decodeForSchemeCheck(url)
    .replace(/[\u0000-\u001F\u007F]/g, "")
    .trim();
  return DANGEROUS_SCHEME_RE.test(normalized);
}

/**
 * Validates user-supplied image URLs (text input, API payloads).
 * Allows http(s) remote URLs and raster data:image/* URLs only.
 */
export function isSafeUserImageUrl(url: string): boolean {
  const trimmed = url?.trim();
  if (!trimmed || trimmed.startsWith("blob:") || hasDangerousScheme(trimmed)) {
    return false;
  }

  try {
    if (trimmed.toLowerCase().startsWith("data:")) {
      const mime = parseDataImageMimeType(trimmed);
      return mime !== null && ALLOWED_RASTER_DATA_IMAGE_TYPES.has(mime);
    }

    const parsed = new URL(trimmed);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Sanitizes a value before binding to img[src].
 * Blob URLs are accepted only when set by the app (URL.createObjectURL).
 * Returns a URL reconstructed by the URL parser so javascript: / vbscript:
 * schemes cannot reach the DOM.
 */
export function sanitizeImagePreviewUrl(
  url: string | null | undefined
): string | null {
  const trimmed = url?.trim();
  if (!trimmed || hasDangerousScheme(trimmed)) {
    return null;
  }

  try {
    if (trimmed.toLowerCase().startsWith("data:")) {
      const mime = parseDataImageMimeType(trimmed);
      return mime !== null && ALLOWED_RASTER_DATA_IMAGE_TYPES.has(mime)
        ? trimmed
        : null;
    }

    const parsed = new URL(trimmed);
    if (
      parsed.protocol === "blob:" ||
      parsed.protocol === "http:" ||
      parsed.protocol === "https:"
    ) {
      return parsed.href;
    }
    return null;
  } catch {
    return null;
  }
}
