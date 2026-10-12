/// <reference types="jest" />

import {
  formatSharePct,
  mergePeriodUsage,
  readInstitutionTokenBreakdown,
  readModelTokenBreakdown,
} from "../../src/utils/llmTokenBreakdown";

const modelRow = {
  service_id: "aug-20-llm-2/Automation",
  task_type: "llm",
  native_units: 10257,
  native_unit_suffix: "tokens",
  native_breakdown: [
    { key: "input", label: "Input tokens", units: 9650, percentage: 94.08 },
    { key: "cached_input", label: "Cached input tokens", units: 150, percentage: 1.46 },
    { key: "output", label: "Output tokens", units: 457, percentage: 4.46 },
  ],
};

describe("readModelTokenBreakdown", () => {
  it("stays collapsed until native_breakdown is present", () => {
    expect(readModelTokenBreakdown({ task_type: "llm", native_units: 4200 })).toBeNull();
    expect(readModelTokenBreakdown({ ...modelRow, native_breakdown: null })).toBeNull();
  });

  it("renders the contract shares and the row total", () => {
    const view = readModelTokenBreakdown(modelRow);
    expect(view?.totalTokens).toBe(10257);
    expect(view?.totalCost).toBeNull();
    expect(view?.categories.map((row) => row.label)).toEqual([
      "Input tokens",
      "Cached input tokens",
      "Output tokens",
    ]);
    expect(view?.categories.map((row) => formatSharePct(row.sharePct))).toEqual([
      "94.08%",
      "1.46%",
      "4.46%",
    ]);
  });

  it("drops a zero cached-input entry and keeps input and output", () => {
    const view = readModelTokenBreakdown({
      native_units: 125,
      native_breakdown: [
        { key: "input", label: "Input tokens", units: 100, percentage: 80 },
        { key: "cached_input", label: "Cached input tokens", units: 0, percentage: 0 },
        { key: "output", label: "Output tokens", units: 25, percentage: 20 },
      ],
    });
    expect(view?.categories.map((row) => row.id)).toEqual(["input", "output"]);
    expect(view?.totalTokens).toBe(125);
  });
});

describe("readInstitutionTokenBreakdown", () => {
  it("reads periodUsage.breakdown cost shares and totals", () => {
    const view = readInstitutionTokenBreakdown({
      taskType: "LLM",
      periodUsage: {
        units: 4200,
        cost: 0.42,
        breakdown: [
          { key: "input", label: "Input tokens", units: 3500, cost: 0.35, costShare: 83.33 },
          {
            key: "cached_input",
            label: "Cached input tokens",
            units: 500,
            cost: 0.02,
            costShare: 4.76,
          },
          { key: "output", label: "Output tokens", units: 200, cost: 0.05, costShare: 11.91 },
        ],
      },
    });
    expect(view?.totalTokens).toBe(4200);
    expect(view?.totalCost).toBe(0.42);
    expect(view?.categories.map((row) => row.cost)).toEqual([0.35, 0.02, 0.05]);
    expect(view?.categories.map((row) => formatSharePct(row.sharePct))).toEqual([
      "83.33%",
      "4.76%",
      "11.91%",
    ]);
  });

  it("omits cached input when the API leaves it out", () => {
    const view = readInstitutionTokenBreakdown({
      periodUsage: {
        units: 31200,
        cost: 3.1,
        breakdown: [
          { key: "input", label: "Input tokens", units: 29000, cost: 2.9, costShare: 93.55 },
          { key: "output", label: "Output tokens", units: 2200, cost: 0.2, costShare: 6.45 },
        ],
      },
    });
    expect(view?.categories.map((row) => row.id)).toEqual(["input", "output"]);
  });

  it("stays collapsed when breakdown is null", () => {
    expect(
      readInstitutionTokenBreakdown({
        periodUsage: { units: 1900, cost: 0.08, breakdown: null },
      }),
    ).toBeNull();
  });
});

describe("mergePeriodUsage", () => {
  it("sums two LLM period splits and recomputes the cost share", () => {
    const merged = mergePeriodUsage([
      {
        periodUsage: {
          units: 100,
          cost: 1,
          breakdown: [
            { key: "input", label: "Input tokens", units: 80, cost: 0.8, costShare: 80 },
            { key: "output", label: "Output tokens", units: 20, cost: 0.2, costShare: 20 },
          ],
        },
      },
      {
        periodUsage: {
          units: 50,
          cost: 1,
          breakdown: [
            { key: "input", label: "Input tokens", units: 50, cost: 1, costShare: 100 },
          ],
        },
      },
    ]);
    expect(merged?.units).toBe(150);
    expect(merged?.cost).toBe(2);
    expect(merged?.breakdown.map((row) => row.units)).toEqual([130, 20]);
    expect(merged?.breakdown.map((row) => row.costShare)).toEqual([90, 10]);
  });
});
