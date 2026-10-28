import {
  cssLengthToPx,
  distributeColumnWidths,
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

  it("grows non-fixed columns in proportion to content when there is room", () => {
    const widths = distributeColumnWidths(cols, 720);
    expect(widths[2]).toBe(120);
    expect(widths[0]).toBe(400);
    expect(widths[1]).toBe(200);
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

  it("never shrinks a text column below its header or the readable minimum", () => {
    const widths = distributeColumnWidths(
      [
        { natural: 400, header: 150, mode: "shrink" },
        { natural: 400, header: 40, mode: "shrink" },
      ],
      100,
    );
    expect(widths).toEqual([150, 128]);
  });
});

describe("resolveColumnSizingMode", () => {
  it("classifies control, short-value and text columns", () => {
    expect(resolveColumnSizingMode({ id: "actions" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "x", width: "120px" })).toBe("fixed");
    expect(resolveColumnSizingMode({ id: "createdAt" })).toBe("content");
    expect(resolveColumnSizingMode({ id: "version" })).toBe("content");
    expect(resolveColumnSizingMode({ id: "name" })).toBe("shrink");
    expect(resolveColumnSizingMode({ id: "email" })).toBe("shrink");
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
