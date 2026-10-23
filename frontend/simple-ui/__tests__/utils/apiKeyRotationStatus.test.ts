import { API_KEY, isApiKeyWithoutLiveValue, resolveApiKeyDisplayStatus } from "../../src/config/constants";
import {
  applyRuntimeConfig,
  EMPTY_RUNTIME_CONFIG,
  getDefaultRotationGraceDays,
} from "../../src/config/runtimeConfig";
import { graceExtensionEnd, graceExtensionError, isRotationInProgress } from "../../src/utils/apiKeyUtils";

const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();

describe("API key rotation status", () => {
  it("a current-revoked key is still active while the previous key works", () => {
    const key = { is_active: true, api_key_revoked_at: inDays(-0.01), rotated_key_expires_at: inDays(2) };
    expect(isApiKeyWithoutLiveValue(key)).toBe(false);
    expect(resolveApiKeyDisplayStatus(key)).toBe(API_KEY.DISPLAY_STATUS.ACTIVE);
    expect(isRotationInProgress(key)).toBe(true);
  });

  it("a current-revoked key is revoked once the previous key's window has ended", () => {
    // The list drops rotated_key_expires_at once the previous value stops.
    const key = { is_active: true, api_key_revoked_at: inDays(-3) };
    expect(isApiKeyWithoutLiveValue(key)).toBe(true);
    expect(resolveApiKeyDisplayStatus(key)).toBe(API_KEY.DISPLAY_STATUS.REVOKED);
  });

  it("a past window end on a current-revoked key also counts as revoked", () => {
    const key = { is_active: true, api_key_revoked_at: inDays(-3), rotated_key_expires_at: inDays(-1) };
    expect(resolveApiKeyDisplayStatus(key)).toBe(API_KEY.DISPLAY_STATUS.REVOKED);
  });

  it("a rotating key with a live current value stays active", () => {
    const key = { is_active: true, rotated_key_expires_at: inDays(2) };
    expect(isApiKeyWithoutLiveValue(key)).toBe(false);
    expect(resolveApiKeyDisplayStatus(key)).toBe(API_KEY.DISPLAY_STATUS.ACTIVE);
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

  it("is null when unset or invalid, so the field starts blank", () => {
    for (const raw of ["", "abc", "-1", "2.5"]) {
      applyRuntimeConfig({ ...EMPTY_RUNTIME_CONFIG, rotationGraceDays: raw });
      expect(getDefaultRotationGraceDays()).toBe(null);
    }
  });
});
