import { EMPTY_VALUE, dash, fmtDate } from "../../src/utils/valueFormatters";

describe("dash", () => {
  it("returns the value when it has content", () => {
    expect(dash("Acme")).toBe("Acme");
  });

  it("falls back to the placeholder for missing or blank values", () => {
    expect(dash(undefined)).toBe(EMPTY_VALUE);
    expect(dash(null)).toBe(EMPTY_VALUE);
    expect(dash("")).toBe(EMPTY_VALUE);
    expect(dash("   ")).toBe(EMPTY_VALUE);
  });
});

describe("fmtDate", () => {
  it("formats a parseable timestamp", () => {
    const iso = "2026-08-14T13:06:00.000Z";
    expect(fmtDate(iso)).toBe(new Date(iso).toLocaleString());
  });

  it("falls back to the placeholder when absent", () => {
    expect(fmtDate(undefined)).toBe(EMPTY_VALUE);
    expect(fmtDate(null)).toBe(EMPTY_VALUE);
    expect(fmtDate("")).toBe(EMPTY_VALUE);
  });

  it("returns the raw value for an unparseable date", () => {
    // Date yields "Invalid Date" instead of throwing, so this needs the NaN check.
    expect(fmtDate("not-a-date")).toBe("not-a-date");
    expect(fmtDate("2026-13-45")).toBe("2026-13-45");
  });
});
