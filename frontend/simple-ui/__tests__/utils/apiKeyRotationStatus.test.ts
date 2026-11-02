import { API_KEY, resolveApiKeyDisplayStatus } from "../../src/config/constants";
import {
  applyRuntimeConfig,
  EMPTY_RUNTIME_CONFIG,
  getDefaultRotationGraceDays,
} from "../../src/config/runtimeConfig";
import {
  graceExtensionEnd,
  graceExtensionError,
  isGraceWithinExpiry,
  isRotationInProgress,
  ROTATION_GRACE_OPTIONS,
} from "../../src/utils/apiKeyUtils";

const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();

describe("API key rotation status", () => {
  it("a rotating key stays active while the previous key works", () => {
    const key = { is_active: true, rotated_key_expires_at: inDays(2) };
    expect(isRotationInProgress(key)).toBe(true);
    expect(resolveApiKeyDisplayStatus(key)).toBe(API_KEY.DISPLAY_STATUS.ACTIVE);
  });
});

describe("rotation grace period options", () => {
  const now = Date.parse("2026-10-10T10:00:00.000Z");

  it("allows every option when the key expires well after them", () => {
    const expiresAt = "2026-10-31T00:00:00.000Z";
    expect(ROTATION_GRACE_OPTIONS.every((d) => isGraceWithinExpiry(d, expiresAt, now))).toBe(true);
  });

  it("disables options that run past the key's expiry", () => {
    const expiresAt = "2026-10-13T10:00:00.000Z"; // 3 days out
    expect(isGraceWithinExpiry(3, expiresAt, now)).toBe(true);
    expect(isGraceWithinExpiry(7, expiresAt, now)).toBe(false);
  });

  it("allows any option for a key that never expires", () => {
    expect(isGraceWithinExpiry(14, undefined, now)).toBe(true);
  });
});

describe("grace period extension", () => {
  const currentEnd = "2026-10-24T12:30:00.000Z";

  it("presets are added to the current end, not to now", () => {
    expect(graceExtensionEnd(currentEnd, "48h", "")?.toISOString()).toBe("2026-10-26T12:30:00.000Z");
    expect(graceExtensionEnd(currentEnd, "7d", "")?.toISOString()).toBe("2026-10-31T12:30:00.000Z");
  });

  it("custom needs a value", () => {
    expect(graceExtensionEnd(currentEnd, "custom", "")).toBe(null);
  });

  it("rejects an end not later than the current one", () => {
    expect(graceExtensionError(new Date(currentEnd), currentEnd, undefined)).toBe(
      "The new end must be later than the current one.",
    );
  });

  it("rejects an end past the key's expiry, allows one equal to it", () => {
    const keyExpiry = "2026-10-25T12:30:00.000Z";
    expect(graceExtensionError(new Date("2026-10-26T12:30:00.000Z"), currentEnd, keyExpiry) !== null).toBe(true);
    expect(graceExtensionError(new Date(keyExpiry), currentEnd, keyExpiry)).toBe(null);
  });
});

describe("default rotation grace days (ROTATED_API_KEY_DEFAULT_GRACE_DAYS)", () => {

  it("parses whole days", () => {
    applyRuntimeConfig({ ...EMPTY_RUNTIME_CONFIG, rotationGraceDays: "7" });
    expect(getDefaultRotationGraceDays()).toBe(7);
    applyRuntimeConfig({ ...EMPTY_RUNTIME_CONFIG, rotationGraceDays: "0" });
    expect(getDefaultRotationGraceDays()).toBe(0);
  });

  it("is null when unset or invalid, so the longest option that fits is preselected", () => {
    for (const raw of ["", "abc", "-1", "2.5"]) {
      applyRuntimeConfig({ ...EMPTY_RUNTIME_CONFIG, rotationGraceDays: raw });
      expect(getDefaultRotationGraceDays()).toBe(null);
    }
  });
});
