/**
 * Validates and returns URLs safe for use as an <img src> attribute.
 * Blocks dangerous protocols (e.g. javascript:) to prevent DOM-based XSS.
 */

const DATA_IMAGE_PREFIX = /^data:image\//i;

export function isSafeImagePreviewUrl(url: string): boolean {
  return getSafeImagePreviewUrl(url) !== null;
}

/**
 * Returns the URL unchanged when safe, or null when it must not be rendered.
 */
export function getSafeImagePreviewUrl(
  url: string | null | undefined
): string | null {
  if (!url || url.trim() === "") {
    return null;
  }

  try {
    if (url.startsWith("blob:")) {
      return url;
    }

    const parsedUrl = new URL(url);

    if (parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:") {
      return url;
    }

    if (parsedUrl.protocol === "data:" && DATA_IMAGE_PREFIX.test(url)) {
      return url;
    }

    return null;
  } catch {
    return null;
  }
}
