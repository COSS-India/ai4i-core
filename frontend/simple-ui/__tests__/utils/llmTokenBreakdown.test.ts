/// <reference types="jest" />

import {
  buildLlmTokenBreakdown,
  formatSharePct,
  readLlmTokenCounts,
} from "../../src/utils/llmTokenBreakdown";

describe("readLlmTokenCounts", () => {
  it("stays empty until the usage API sends input or output tokens", () => {
    expect(readLlmTokenCounts({ taskType: "llm", consumed: 4200 })).toBeNull();
  });

  it("reads a snake_case token_breakdown", () => {
    expect(
      readLlmTokenCounts({
        token_breakdown: {
          input_tokens: 9650,
          cached_input_tokens: 150,
          output_tokens: 457,
        },
      }),
    ).toMatchObject({
      inputTokens: 9650,
      cachedInputTokens: 150,
      outputTokens: 457,
    });
  });

  it("reads camelCase costs on the row itself", () => {
    expect(
      readLlmTokenCounts({
        inputTokens: 3500,
        outputTokens: 200,
        inputCost: 0.35,
        outputCost: 0.05,
      }),
    ).toMatchObject({
      inputTokens: 3500,
      cachedInputTokens: null,
      outputTokens: 200,
      inputCost: 0.35,
      outputCost: 0.05,
    });
  });
});

describe("buildLlmTokenBreakdown", () => {
  it("matches the model drill-down shares and keeps the parent total", () => {
    const view = buildLlmTokenBreakdown(
      {
        inputTokens: 9650,
        cachedInputTokens: 150,
        outputTokens: 457,
        inputCost: null,
        cachedInputCost: null,
        outputCost: null,
      },
      false,
    );
    expect(view.totalTokens).toBe(10257);
    expect(view.categories.map((row) => row.label)).toEqual([
      "Input tokens",
      "Cached input tokens",
      "Output tokens",
    ]);
    expect(view.categories.map((row) => formatSharePct(row.sharePct ?? 0))).toEqual([
      "94.08%",
      "1.46%",
      "4.46%",
    ]);
  });

  it("omits cached input when it is zero or missing, and still counts it as zero", () => {
    const missing = buildLlmTokenBreakdown(
      {
        inputTokens: 100,
        cachedInputTokens: null,
        outputTokens: 25,
        inputCost: null,
        cachedInputCost: null,
        outputCost: null,
      },
      false,
    );
    const zero = buildLlmTokenBreakdown(
      {
        inputTokens: 100,
        cachedInputTokens: 0,
        outputTokens: 25,
        inputCost: null,
        cachedInputCost: null,
        outputCost: null,
      },
      false,
    );
    expect(missing.categories.map((row) => row.id)).toEqual(["input", "output"]);
    expect(zero.categories.map((row) => row.id)).toEqual(["input", "output"]);
    expect(missing.totalTokens).toBe(125);
    expect(zero.totalTokens).toBe(125);
  });

  it("shares the institution row by usage cost and totals tokens and cost", () => {
    const view = buildLlmTokenBreakdown(
      {
        inputTokens: 3500,
        cachedInputTokens: 500,
        outputTokens: 200,
        inputCost: 0.35,
        cachedInputCost: 0.02,
        outputCost: 0.05,
      },
      true,
    );
    expect(view.totalTokens).toBe(4200);
    expect(view.totalCost).toBeCloseTo(0.42);
    expect(view.categories.map((row) => formatSharePct(row.sharePct ?? 0))).toEqual([
      "83.33%",
      "4.76%",
      "11.90%",
    ]);
  });

  it("leaves the cost share blank when the API has not sent costs yet", () => {
    const view = buildLlmTokenBreakdown(
      {
        inputTokens: 10,
        cachedInputTokens: null,
        outputTokens: 5,
        inputCost: null,
        cachedInputCost: null,
        outputCost: null,
      },
      true,
    );
    expect(view.totalCost).toBeNull();
    expect(view.categories.every((row) => row.sharePct == null && row.cost == null)).toBe(
      true,
    );
  });
});
