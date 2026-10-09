import { normalizeModelTaskType } from "./meteringTaskType";

/**
 * LLM token split for the Usage Dashboard drill-downs (AI4IDS-3339).
 *
 * The usage API contract is not published yet. `readLlmTokenCounts` is the
 * only place that knows the wire names. Until a row carries input and output
 * counts, it returns null and the row stays collapsed.
 */

export type LlmTokenCategoryId = "input" | "cachedInput" | "output";

export interface LlmTokenCounts {
  inputTokens: number;
  /** Null when cached input was not reported. Zero is reported and still hidden. */
  cachedInputTokens: number | null;
  outputTokens: number;
  inputCost: number | null;
  cachedInputCost: number | null;
  outputCost: number | null;
}

export interface LlmTokenCategoryView {
  id: LlmTokenCategoryId;
  label: string;
  tokens: number;
  cost: number | null;
  /** Null when usage cost was not reported, so a share cannot be computed. */
  sharePct: number | null;
}

export interface LlmTokenBreakdownView {
  categories: LlmTokenCategoryView[];
  totalTokens: number;
  totalCost: number | null;
}

const CATEGORY_LABEL: Record<LlmTokenCategoryId, string> = {
  input: "Input tokens",
  cachedInput: "Cached input tokens",
  output: "Output tokens",
};

export function isLlmTaskType(taskType: string | null | undefined): boolean {
  return normalizeModelTaskType(taskType) === "llm";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function finiteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

/** First present numeric field. Absent and null both mean "not reported". */
function pickCount(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(record, key)) continue;
    return finiteNumber(record[key]);
  }
  return null;
}

function nonNegative(value: number): number {
  return value < 0 ? 0 : value;
}

/**
 * Reads a token split from a model-consumption row or an institution task row.
 * Accepts snake_case or camelCase, nested under `token_breakdown` /
 * `tokenBreakdown`, or flat on the row. Returns null when input and output
 * are both missing — that is the "API not ready" case.
 */
export function readLlmTokenCounts(source: object): LlmTokenCounts | null {
  const row = asRecord(source);
  if (!row) return null;
  const nested =
    asRecord(row.token_breakdown) ?? asRecord(row.tokenBreakdown) ?? row;

  const inputTokens = pickCount(nested, ["input_tokens", "inputTokens"]);
  const outputTokens = pickCount(nested, ["output_tokens", "outputTokens"]);
  if (inputTokens == null && outputTokens == null) return null;

  return {
    inputTokens: nonNegative(inputTokens ?? 0),
    cachedInputTokens: (() => {
      const cached = pickCount(nested, [
        "cached_input_tokens",
        "cachedInputTokens",
      ]);
      return cached == null ? null : nonNegative(cached);
    })(),
    outputTokens: nonNegative(outputTokens ?? 0),
    inputCost: pickCount(nested, ["input_cost", "inputCost"]),
    cachedInputCost: pickCount(nested, [
      "cached_input_cost",
      "cachedInputCost",
    ]),
    outputCost: pickCount(nested, ["output_cost", "outputCost"]),
  };
}

function shareOf(part: number, total: number): number {
  if (total <= 0) return 0;
  return (part / total) * 100;
}

/**
 * Visible categories for one LLM row.
 * Cached input is omitted when it is zero or was not reported. It still
 * counts as zero in the token total. Shares are of total tokens, or of
 * total usage cost when `shareOfCost` is set.
 */
export function buildLlmTokenBreakdown(
  counts: LlmTokenCounts,
  shareOfCost: boolean,
): LlmTokenBreakdownView {
  const cachedTokens = counts.cachedInputTokens ?? 0;
  const showCached = counts.cachedInputTokens != null && counts.cachedInputTokens > 0;
  const totalTokens = counts.inputTokens + cachedTokens + counts.outputTokens;

  const reportedCosts = [
    counts.inputCost,
    showCached ? counts.cachedInputCost : null,
    counts.outputCost,
  ];
  const costsReported = shareOfCost && reportedCosts.some((cost) => cost != null);
  const costOrZero = (cost: number | null) => (costsReported ? (cost ?? 0) : null);
  const inputCost = costOrZero(counts.inputCost);
  const cachedCost = showCached ? costOrZero(counts.cachedInputCost) : null;
  const outputCost = costOrZero(counts.outputCost);
  const totalCost = costsReported
    ? (inputCost ?? 0) + (showCached ? (cachedCost ?? 0) : 0) + (outputCost ?? 0)
    : null;

  const draft: Array<{
    id: LlmTokenCategoryId;
    tokens: number;
    cost: number | null;
  }> = [
    { id: "input", tokens: counts.inputTokens, cost: inputCost },
    ...(showCached
      ? [{ id: "cachedInput" as const, tokens: counts.cachedInputTokens ?? 0, cost: cachedCost }]
      : []),
    { id: "output", tokens: counts.outputTokens, cost: outputCost },
  ];

  return {
    totalTokens,
    totalCost,
    categories: draft.map((category) => ({
      id: category.id,
      label: CATEGORY_LABEL[category.id],
      tokens: category.tokens,
      cost: category.cost,
      sharePct: shareOfCost
        ? totalCost == null
          ? null
          : shareOf(category.cost ?? 0, totalCost)
        : shareOf(category.tokens, totalTokens),
    })),
  };
}

/** Sums two splits. A missing cached count stays missing only when both sides omitted it. */
export function mergeLlmTokenCounts(
  left: LlmTokenCounts | null,
  right: LlmTokenCounts | null,
): LlmTokenCounts | null {
  if (!left) return right;
  if (!right) return left;
  const sumCost = (a: number | null, b: number | null) =>
    a == null && b == null ? null : (a ?? 0) + (b ?? 0);
  return {
    inputTokens: left.inputTokens + right.inputTokens,
    outputTokens: left.outputTokens + right.outputTokens,
    cachedInputTokens:
      left.cachedInputTokens == null && right.cachedInputTokens == null
        ? null
        : (left.cachedInputTokens ?? 0) + (right.cachedInputTokens ?? 0),
    inputCost: sumCost(left.inputCost, right.inputCost),
    cachedInputCost: sumCost(left.cachedInputCost, right.cachedInputCost),
    outputCost: sumCost(left.outputCost, right.outputCost),
  };
}

/** Writes a split back onto a row using the camelCase names the reader accepts. */
export function withLlmTokenCounts<T extends object>(
  row: T,
  counts: LlmTokenCounts,
): T & LlmTokenCounts {
  return { ...row, ...counts };
}

export function formatTokenCount(value: number): string {
  return value.toLocaleString("en-IN");
}

/** Usage cost can be a fraction of a rupee; budget figures stay whole units. */
export function formatTokenUsageCost(value: number, currency = "INR"): string {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `₹${value.toFixed(2)}`;
  }
}

export function formatSharePct(pct: number): string {
  return `${pct.toFixed(2)}%`;
}
