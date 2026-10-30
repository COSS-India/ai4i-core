import {
  cssLengthToPx,
  distributeColumnWidths,
  measureColumnNaturalWidths,
  resolveColumnSizingMode,
  type ColumnSizingInput,
} from "../../src/components/common/dataTableUtils";

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);

describe("distributeColumnWidths", () => {
  it("spreads leftover width evenly across flexible columns (actions stay fixed)", () => {
    const widths = distributeColumnWidths(
      [
        { natural: 200, header: 60, mode: "shrink" },
        { natural: 100, header: 80, mode: "shrink" },
        { natural: 120, header: 70, mode: "fixed" },
      ],
      720,
    );
    // extra = 720 - 420 = 300 → +150 each shrink column
    expect(widths[0]).toBe(350);
    expect(widths[1]).toBe(250);
    expect(widths[2]).toBe(120);
    expect(sum(widths)).toBe(720);
  });

  it("lets price columns share leftover space instead of staying pinned", () => {
    expect(resolveColumnSizingMode({ id: "inputPrice" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "outputPrice" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "cached_input_price" })).toBe("shrink");

    const widths = distributeColumnWidths(
      [
        { natural: 220, header: 60, mode: "shrink" }, // name
        { natural: 110, header: 90, mode: "shrink" }, // input
        { natural: 110, header: 90, mode: "shrink" }, // output
        { natural: 110, header: 90, mode: "shrink" }, // cached
        { natural: 156, header: 156, mode: "fixed" }, // actions
      ],
      900,
    );
    // All four flexible columns grow by roughly the same amount (±1px remainder)
    const growth = widths.slice(0, 4).map((w, i) => w - [220, 110, 110, 110][i]);
    const maxGrowth = Math.max(...growth);
    const minGrowth = Math.min(...growth);
    expect(maxGrowth - minGrowth).toBeLessThanOrEqual(1);
    expect(minGrowth).toBeGreaterThan(0);
    expect(widths[4]).toBe(156);
    expect(sum(widths)).toBe(900);
  });

  it("shrinks flexible columns when space is tight and keeps actions fixed", () => {
    const widths = distributeColumnWidths(
      [
        { natural: 200, header: 60, mode: "shrink" },
        { natural: 100, header: 80, mode: "shrink" },
        { natural: 120, header: 70, mode: "fixed" },
      ],
      380,
    );
    expect(widths[2]).toBe(120);
    expect(sum(widths)).toBeLessThanOrEqual(380);
    expect(widths[0]).toBeGreaterThan(0);
    expect(widths[1]).toBeGreaterThan(0);
  });

  it("levels the widest text column first", () => {
    const widths = distributeColumnWidths(
      [
        { natural: 600, header: 50, mode: "shrink" },
        { natural: 150, header: 50, mode: "shrink" },
      ],
      500,
    );
    expect(widths[1]).toBe(150);
    expect(widths[0]).toBe(350);
  });

  it("scales to fit the viewport when floors would otherwise overflow", () => {
    const roomy = distributeColumnWidths(
      [
        { natural: 400, header: 150, mode: "shrink" },
        { natural: 400, header: 40, mode: "shrink" },
      ],
      300,
    );
    expect(sum(roomy)).toBeLessThanOrEqual(300);

    const tight = distributeColumnWidths(
      [
        { natural: 400, header: 150, mode: "shrink" },
        { natural: 400, header: 40, mode: "shrink" },
      ],
      100,
    );
    expect(sum(tight)).toBeLessThanOrEqual(100);
    expect(tight.every((w) => w >= 1)).toBe(true);
  });
});

describe("resolveColumnSizingMode", () => {
  it("only pins actions and explicit widths; data columns stay flexible", () => {
    expect(resolveColumnSizingMode({ id: "actions" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "x", width: "120px" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "task" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "status" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "createdAt" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "name" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "email" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "inputPrice" })).toBe("shrink");
  });
});

describe("measureColumnNaturalWidths", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("flags columns hidden at the current breakpoint", () => {
    document.body.innerHTML = `
      <table>
        <thead><tr><th>Key</th><th style="display:none">Permissions</th><th>Actions</th></tr></thead>
        <tbody><tr><td>abc</td><td style="display:none">read</td><td>edit</td></tr></tbody>
      </table>`;
    const table = document.querySelector("table") as HTMLTableElement;
    const measured = measureColumnNaturalWidths(table, 3);
    expect(measured?.visible).toEqual([true, false, true]);
  });
});

describe("cssLengthToPx", () => {
  it("parses px and rem, ignores relative units", () => {
    expect(cssLengthToPx("36px")).toBe(36);
    expect(cssLengthToPx("2.25rem")).toBe(36);
    expect(cssLengthToPx("20%")).toBeUndefined();
    expect(cssLengthToPx(undefined)).toBeUndefined();
  });
});
