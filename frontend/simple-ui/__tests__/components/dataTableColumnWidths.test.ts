import {
  cssLengthToPx,
  distributeColumnWidths,
  measureColumnNaturalWidths,
  resolveColumnSizingMode,
  type ColumnSizingInput,
} from "../../src/components/common/dataTableUtils";

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);

describe("distributeColumnWidths", () => {
  const cols: ColumnSizingInput[] = [
    { natural: 200, header: 60, mode: "shrink" },
    { natural: 100, header: 80, mode: "content" },
    { natural: 120, header: 70, mode: "fixed" },
  ];

  it("gives leftover space only to shrink columns", () => {
    const widths = distributeColumnWidths(cols, 720);
    expect(widths[2]).toBe(120);
    expect(widths[1]).toBe(100);
    expect(widths[0]).toBe(500);
    expect(sum(widths)).toBeLessThanOrEqual(720);
  });

  it("treats price columns as shrinkable, not content-locked", () => {
    expect(resolveColumnSizingMode({ id: "inputPrice" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "cached_input_price" })).toBe("shrink");
  });

  it("shrinks only text columns when space is tight, keeping content columns whole", () => {
    const widths = distributeColumnWidths(cols, 380);
    expect(widths[1]).toBe(100);
    expect(widths[2]).toBe(120);
    expect(widths[0]).toBe(160);
    expect(sum(widths)).toBeLessThanOrEqual(380);
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
    expect(roomy[0]).toBeGreaterThanOrEqual(150);
    expect(roomy[1]).toBeGreaterThanOrEqual(128);
    expect(sum(roomy)).toBeLessThanOrEqual(300);

    const tight = distributeColumnWidths(
      [
        { natural: 400, header: 150, mode: "shrink" },
        { natural: 400, header: 40, mode: "shrink" },
      ],
      100,
    );
    expect(sum(tight)).toBeLessThanOrEqual(100);
    expect(tight.every((w) => w >= 40)).toBe(true);
  });
});

describe("resolveColumnSizingMode", () => {
  it("classifies control, compact badge, and text columns", () => {
    expect(resolveColumnSizingMode({ id: "actions" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "x", width: "120px" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "task" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "status" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "createdAt" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "name" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "email" })).toBe("shrink");
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
