import { normalizeModelTaskType } from "./meteringTaskType";

/**
 * LLM token split for the Usage Dashboard drill-downs (AI4IDS-3339).
 *
 * Model rows read `native_breakdown` (TokenShare: units + percentage).
 * Institution rows read `periodUsage.breakdown` (CostShare: units, cost, costShare)
 * and the Total row from `periodUsage.units` / `periodUsage.cost`.
 * Cached input is omitted by the API when it is zero; a zero entry is dropped here too.
 */

export type LlmTokenCategoryId = "input" | "cached_input" | "output";

export interface LlmTokenCategoryView {
  id: LlmTokenCategoryId;
  label: string;
  tokens: number;
  cost: number | null;
  /** Model: share of total tokens. Institution: share of total usage cost. */
  sharePct: number;
}

export interface LlmTokenBreakdownView {
  categories: LlmTokenCategoryView[];
  totalTokens: number;
  totalCost: number | null;
}

const CATEGORY_ORDER: LlmTokenCategoryId[] = ["input", "cached_input", "output"];

const CATEGORY_LABEL: Record<LlmTokenCategoryId, string> = {
  input: "Input tokens",
  cached_input: "Cached input tokens",
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

function isCategoryId(value: string): value is LlmTokenCategoryId {
  return (CATEGORY_ORDER as string[]).includes(value);
}

function readShareEntries(
  value: unknown,
  shareField: "percentage" | "costShare",
  withCost: boolean,
): LlmTokenCategoryView[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const categories: LlmTokenCategoryView[] = [];
  for (const item of value) {
    const row = asRecord(item);
    if (!row || typeof row.key !== "string" || !isCategoryId(row.key)) continue;
    const units = finiteNumber(row.units);
    if (units == null) continue;
    const tokens = units < 0 ? 0 : units;
    if (row.key === "cached_input" && tokens <= 0) continue;
    const share = finiteNumber(row[shareField]);
    const cost = withCost ? finiteNumber(row.cost) : null;
    const label =
      typeof row.label === "string" && row.label.trim()
        ? row.label
        : CATEGORY_LABEL[row.key];
    categories.push({
      id: row.key,
      label,
      tokens,
      cost,
      sharePct: share ?? 0,
    });
  }
  if (categories.length === 0) return null;
  categories.sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.id) - CATEGORY_ORDER.indexOf(b.id),
  );
  return categories;
}

function summedTokens(categories: LlmTokenCategoryView[]): number {
  return categories.reduce((sum, category) => sum + category.tokens, 0);
}

/** Model drill-down. Null when `native_breakdown` is absent (non-LLM, or not sent yet). */
export function readModelTokenBreakdown(source: object): LlmTokenBreakdownView | null {
  const row = asRecord(source);
  if (!row) return null;
  const categories = readShareEntries(row.native_breakdown, "percentage", false);
  if (!categories) return null;
  return {
    categories,
    totalTokens: finiteNumber(row.native_units) ?? summedTokens(categories),
    totalCost: null,
  };
}

/** Institution drill-down. Null when `periodUsage.breakdown` is absent. */
export function readInstitutionTokenBreakdown(
  source: object,
): LlmTokenBreakdownView | null {
  const row = asRecord(source);
  const period = row ? asRecord(row.periodUsage) : null;
  if (!period) return null;
  const categories = readShareEntries(period.breakdown, "costShare", true);
  if (!categories) return null;
  const summedCost = categories.reduce(
    (sum, category) => sum + (category.cost ?? 0),
    0,
  );
  return {
    categories,
    totalTokens: finiteNumber(period.units) ?? summedTokens(categories),
    totalCost: finiteNumber(period.cost) ?? summedCost,
  };
}

/**
 * Sums `periodUsage` across task rows that share a task type.
 * Cost shares are recomputed from the summed costs.
 */
export function mergePeriodUsage(sources: object[]): {
  units: number;
  cost: number;
  breakdown: Array<{
    key: LlmTokenCategoryId;
    label: string;
    units: number;
    cost: number;
    costShare: number;
  }>;
} | null {
  const views = sources
    .map((source) => readInstitutionTokenBreakdown(source))
    .filter((view): view is LlmTokenBreakdownView => view != null);
  if (views.length === 0) return null;

  const byId = new Map<LlmTokenCategoryId, LlmTokenCategoryView>();
  for (const view of views) {
    for (const category of view.categories) {
      const existing = byId.get(category.id);
      if (!existing) {
        byId.set(category.id, { ...category, cost: category.cost ?? 0 });
      } else {
        existing.tokens += category.tokens;
        existing.cost = (existing.cost ?? 0) + (category.cost ?? 0);
      }
    }
  }
  const categories = CATEGORY_ORDER.flatMap((id) => {
    const category = byId.get(id);
    return category ? [category] : [];
  });
  const units = views.reduce((sum, view) => sum + view.totalTokens, 0);
  const cost = views.reduce((sum, view) => sum + (view.totalCost ?? 0), 0);
  return {
    units,
    cost,
    breakdown: categories.map((category) => ({
      key: category.id,
      label: category.label,
      units: category.tokens,
      cost: category.cost ?? 0,
      costShare: cost > 0 ? ((category.cost ?? 0) / cost) * 100 : 0,
    })),
  };
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
