/// <reference types="jest" />

import { toDisplayAttributes } from "../../src/utils/spanAttributes";

describe("toDisplayAttributes", () => {
  it("shows metadata_kv as the metadata object the caller sent", () => {
    const shown = toDisplayAttributes({
      status: "success",
      metadata_kv: ["metakey_1=metavalue_1", "metakey_2=metavalue_2"],
      total_time_ms: 12,
    });
    expect(shown).toEqual({
      status: "success",
      metadata: { metakey_1: "metavalue_1", metakey_2: "metavalue_2" },
      total_time_ms: 12,
    });
    expect(Object.keys(shown)).toEqual(["status", "metadata", "total_time_ms"]);
  });

  it("splits at the first '=' so values may contain it", () => {
    expect(toDisplayAttributes({ metadata_kv: ["q=a=b", "empty="] })).toEqual({
      metadata: { q: "a=b", empty: "" },
    });
  });

  it("leaves attributes untouched when there is nothing to convert", () => {
    const plain = { status: "ok" };
    expect(toDisplayAttributes(plain)).toBe(plain);
  });

  it("leaves malformed or clashing metadata_kv as stored", () => {
    const malformed = { metadata_kv: ["no-separator"] };
    expect(toDisplayAttributes(malformed)).toBe(malformed);
    const clash = { metadata: "x", metadata_kv: ["a=b"] };
    expect(toDisplayAttributes(clash)).toBe(clash);
  });
});
