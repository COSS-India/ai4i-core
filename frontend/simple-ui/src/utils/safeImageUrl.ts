/** Raster image MIME types allowed in data: URLs (SVG excluded — scriptable content). */
const ALLOWED_RASTER_DATA_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/gif",
  "image/webp",
]);

function parseDataImageMimeType(url: string): string | null {
  const match = url.match(/^data:(image\/[^;,]+)/i);
  return match ? match[1].toLowerCase() : null;
}

/**
 * Validates user-supplied image URLs (text input, API payloads).
 * Allows http(s) remote URLs and raster data:image/* URLs only.
 */
export function isSafeUserImageUrl(url: string): boolean {
  const trimmed = url?.trim();
  if (!trimmed) {
    return false;
  }

  if (trimmed.startsWith("blob:")) {
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
 */
export function sanitizeImagePreviewUrl(
  url: string | null | undefined
): string | null {
  const trimmed = url?.trim();
  if (!trimmed) {
    return null;
  }

  if (trimmed.startsWith("blob:")) {
    return trimmed;
  }

  return isSafeUserImageUrl(trimmed) ? trimmed : null;
}
