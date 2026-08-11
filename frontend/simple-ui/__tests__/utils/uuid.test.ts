/// <reference types="jest" />

import { generateUUID } from "../../src/utils/uuid";

// 8-4-4-4-12 hex, version nibble "4", variant nibble one of 8, 9, a, b.
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("generateUUID", () => {
  const realCrypto = window.crypto;

  const setCrypto = (value: unknown) => {
    Object.defineProperty(window, "crypto", {
      value,
      configurable: true,
      writable: true,
    });
  };

  afterEach(() => {
    setCrypto(realCrypto);
  });

  it("uses crypto.randomUUID when the browser exposes it", () => {
    const randomUUID = jest.fn(() => "11111111-2222-4333-8444-555555555555");
    setCrypto({
      randomUUID,
      getRandomValues: (arr: Uint8Array) => realCrypto.getRandomValues(arr),
    });

    expect(generateUUID()).toBe("11111111-2222-4333-8444-555555555555");
    expect(randomUUID).toHaveBeenCalledTimes(1);
  });

  // On an insecure origin (the portal served over plain HTTP) the browser does
  // not expose crypto.randomUUID at all. getRandomValues stays available.
  it("falls back to getRandomValues when randomUUID is missing", () => {
    setCrypto({
      getRandomValues: (arr: Uint8Array) => realCrypto.getRandomValues(arr),
    });

    expect(() => generateUUID()).not.toThrow();
    expect(generateUUID()).toMatch(UUID_V4);
  });

  it("produces unique ids on the fallback path", () => {
    setCrypto({
      getRandomValues: (arr: Uint8Array) => realCrypto.getRandomValues(arr),
    });

    const ids = new Set(Array.from({ length: 200 }, () => generateUUID()));
    expect(ids.size).toBe(200);
  });
});
