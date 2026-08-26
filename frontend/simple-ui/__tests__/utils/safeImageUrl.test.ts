/// <reference types="jest" />

import {
  isSafeUserImageUrl,
  sanitizeImagePreviewUrl,
} from "../../src/utils/safeImageUrl";

describe("isSafeUserImageUrl", () => {
  it("allows http and https image URLs", () => {
    expect(isSafeUserImageUrl("https://example.com/photo.jpg")).toBe(true);
    expect(isSafeUserImageUrl("http://example.com/photo.png")).toBe(true);
  });

  it("allows raster data:image URLs", () => {
    expect(isSafeUserImageUrl("data:image/png;base64,abc")).toBe(true);
    expect(isSafeUserImageUrl("data:image/jpeg;base64,abc")).toBe(true);
  });

  it("rejects dangerous protocols and scriptable image types", () => {
    expect(isSafeUserImageUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeUserImageUrl("javascript%3Aalert(1)")).toBe(false);
    expect(isSafeUserImageUrl("vbscript:msgbox(1)")).toBe(false);
    expect(isSafeUserImageUrl("data:text/html,<script>alert(1)</script>")).toBe(
      false
    );
    expect(
      isSafeUserImageUrl("data:image/svg+xml,<svg onload=alert(1)>")
    ).toBe(false);
    expect(isSafeUserImageUrl("blob:https://example.com/uuid")).toBe(false);
    expect(isSafeUserImageUrl("")).toBe(false);
    expect(isSafeUserImageUrl("not-a-url")).toBe(false);
  });
});

describe("sanitizeImagePreviewUrl", () => {
  it("passes through app-generated blob URLs", () => {
    const blobUrl = "blob:http://localhost:3000/abc-123";
    expect(sanitizeImagePreviewUrl(blobUrl)).toBe(blobUrl);
  });

  it("sanitizes user URLs at the render sink", () => {
    expect(sanitizeImagePreviewUrl("https://example.com/a.jpg")).toBe(
      encodeURI("https://example.com/a.jpg")
    );
    expect(sanitizeImagePreviewUrl("javascript:alert(1)")).toBeNull();
    expect(sanitizeImagePreviewUrl("javascript%3Aalert(1)")).toBeNull();
    expect(sanitizeImagePreviewUrl("vbscript:msgbox(1)")).toBeNull();
    expect(sanitizeImagePreviewUrl(null)).toBeNull();
    expect(sanitizeImagePreviewUrl("  ")).toBeNull();
  });
});
