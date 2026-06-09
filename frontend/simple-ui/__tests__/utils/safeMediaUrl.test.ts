import {
  getSafeImagePreviewUrl,
  isSafeImagePreviewUrl,
} from "@/utils/safeMediaUrl";

describe("safeMediaUrl", () => {
  describe("getSafeImagePreviewUrl", () => {
    it("returns null for empty values", () => {
      expect(getSafeImagePreviewUrl(null)).toBeNull();
      expect(getSafeImagePreviewUrl(undefined)).toBeNull();
      expect(getSafeImagePreviewUrl("")).toBeNull();
      expect(getSafeImagePreviewUrl("   ")).toBeNull();
    });

    it("allows blob URLs from createObjectURL", () => {
      const blobUrl = "blob:http://localhost:3000/abc-123";
      expect(getSafeImagePreviewUrl(blobUrl)).toBe(blobUrl);
    });

    it("allows http and https image URLs", () => {
      expect(getSafeImagePreviewUrl("https://example.com/image.png")).toBe(
        "https://example.com/image.png"
      );
      expect(getSafeImagePreviewUrl("http://example.com/image.jpg")).toBe(
        "http://example.com/image.jpg"
      );
    });

    it("allows data:image/* URLs", () => {
      const dataUrl =
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
      expect(getSafeImagePreviewUrl(dataUrl)).toBe(dataUrl);
    });

    it("blocks javascript: and other dangerous protocols", () => {
      expect(getSafeImagePreviewUrl("javascript:alert(1)")).toBeNull();
      expect(getSafeImagePreviewUrl("vbscript:msgbox(1)")).toBeNull();
    });

    it("blocks non-image data URLs", () => {
      expect(
        getSafeImagePreviewUrl("data:text/html,<script>alert(1)</script>")
      ).toBeNull();
      expect(getSafeImagePreviewUrl("data:application/json,{}")).toBeNull();
    });

    it("blocks malformed URLs", () => {
      expect(getSafeImagePreviewUrl("not-a-valid-url")).toBeNull();
    });
  });

  describe("isSafeImagePreviewUrl", () => {
    it("mirrors getSafeImagePreviewUrl", () => {
      expect(isSafeImagePreviewUrl("https://example.com/a.png")).toBe(true);
      expect(isSafeImagePreviewUrl("javascript:alert(1)")).toBe(false);
    });
  });
});
