/// <reference types="jest" />

import {
  parsePricePerUnit,
  PRICE_PER_UNIT_MAX,
  validatePricePerUnit,
} from "../../src/components/services-management/serviceFormValidation";

describe("validatePricePerUnit", () => {
  it("keeps the single-price label for non-LLM services", () => {
    expect(validatePricePerUnit("")).toBe("Price per unit size is required.");
    expect(validatePricePerUnit("-1")).toBe(
      "Price per unit size must be 0 or greater.",
    );
  });

  it("names each LLM token price in the inline error", () => {
    expect(validatePricePerUnit("  ", "Input Token Price")).toBe(
      "Input Token Price is required.",
    );
    expect(validatePricePerUnit("-0.5", "Cached Input Token Price")).toBe(
      "Cached Input Token Price must be 0 or greater.",
    );
    expect(validatePricePerUnit("nope", "Output Token Price")).toBe(
      "Output Token Price must be a number.",
    );
  });

  it("allows zero and rejects a price above the shared cap", () => {
    expect(validatePricePerUnit("0", "Input Token Price")).toBeNull();
    expect(
      validatePricePerUnit(String(PRICE_PER_UNIT_MAX), "Output Token Price"),
    ).toBeNull();
    expect(
      validatePricePerUnit(String(PRICE_PER_UNIT_MAX + 1), "Output Token Price"),
    ).toMatch(/must not exceed/);
  });
});

describe("parsePricePerUnit", () => {
  it("keeps zero and drops a blank field", () => {
    expect(parsePricePerUnit("0")).toBe(0);
    expect(parsePricePerUnit(" 40.5 ")).toBe(40.5);
    expect(parsePricePerUnit("")).toBeUndefined();
    expect(parsePricePerUnit("   ")).toBeUndefined();
  });
});
