import { METERING } from "../config/meteringConstants";
import { meteringColorAt } from "./meteringColors";
import type {
  SpendByTaskType,
  TenantTierBreakdown,
  TenantUsageAggregate,
  TenantUsageDetail,
  UsageSummaryResponse,
} from "../types/usageSpend";

type TaskTypeColorKey = keyof typeof METERING.COLORS.TASK_TYPE;

export const USAGE_SPEND_STALE_MS = 60_000;
export const USAGE_SPEND_ACCENT = "#2a67d6";
export const USAGE_SPEND_DANGER = "#c0392b";
export const USAGE_SPEND_WARNING = "#b8720a";

const AVATAR_COLORS = [
  "#d6336c",
  "#2f9e44",
  "#f08c00",
  "#1971c2",
  "#7048e8",
  "#e8590c",
  "#0ca678",
  "#74b816",
] as const;

export type BillingPeriodKey = "current" | "last";

export interface AggregatedTaskUsage {
  taskType: string;
  unit: string;
  quotaLimit?: number | null;
  consumed: number;
  remaining?: number | null;
  spend: number;
}

/** True when the API populated the flat quota-bar fields for one homogeneous unit. */
export function hasPopulatedQuotaUsage(usage: TenantUsageAggregate): boolean {
  return (
    usage.consumed != null &&
    usage.quotaLimit != null &&
    usage.unit != null &&
    usage.unit !== "Units"
  );
}

/** True when the tenant consumed multiple model task types — per-type quota only. */
export function isMultiTaskQuotaTenant(usage: TenantUsageAggregate): boolean {
  return usage.taskTypeCount > 1;
}

export function billingPeriodValue(key: BillingPeriodKey): string {
  const d = new Date();
  if (key === "last") d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function billingPeriodLabel(key: BillingPeriodKey): string {
  return key === "current" ? "CURRENT MONTH" : "LAST MONTH";
}

/** Budget and spend figures display as whole currency units — decimals rounded away. */
export function formatSpendMoney(n: number, currency = "INR"): string {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `₹${Math.round(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  }
}

const UNIT_SHORT_LABEL: Record<string, string> = {
  tokens: "tokens",
  characters: "chars",
  audio_minutes: "min",
  minutes: "min",
  images: "imgs",
  requests: "reqs",
};

export function shortUnitLabel(unit: string): string {
  const u = (unit || "").trim().toLowerCase();
  return UNIT_SHORT_LABEL[u] ?? (unit || "").trim();
}

function compactCount(n: number): string {
  const abs = Math.abs(n);
  const scaled = (div: number, suffix: string) =>
    `${(n / div).toFixed(1).replace(/\.0$/, "")}${suffix}`;
  if (abs >= 999.95e6) return scaled(1e9, "B");
  if (abs >= 999.95e3) return scaled(1e6, "M");
  if (abs >= 999.5) return scaled(1e3, "K");
  return String(Math.round(n));
}

export function formatSpendUnit(n: number, unit: string): string {
  const u = (unit || "").toLowerCase();
  if (u === "tokens" || u === "characters") {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M ${unit}`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K ${unit}`;
    return `${Math.round(n)} ${unit}`;
  }
  if (u === "minutes") return `${Math.round(n).toLocaleString("en-IN")} min`;
  return `${Math.round(n).toLocaleString("en-IN")} ${unit || ""}`.trim();
}

export function formatSpendUnitCompact(n: number, unit: string): string {
  return `${compactCount(n)} ${shortUnitLabel(unit)}`.trim();
}

/** Exact locale-grouped figure — recovers what `formatSpendUnitCompact` rounds away. */
export function formatSpendUnitExact(n: number, unit: string): string {
  return `${Math.round(n).toLocaleString("en-IN")} ${shortUnitLabel(unit)}`.trim();
}

export interface SpendTokenTotals {
  unit: string;
  tokensAllocated: number | null;
  tokensUsed: number | null;
  tokensRemaining: number | null;
}

/** Mixed-unit scope has no meaningful total; every figure dashes out. */
const NO_TOKEN_TOTALS: SpendTokenTotals = {
  unit: "",
  tokensAllocated: null,
  tokensUsed: null,
  tokensRemaining: null,
};

/**
 * Totals only when every row shares one unit. Task types are metered in tokens,
 * audio_minutes, characters, images or requests (inference_types.yaml), so summing
 * across a mixed set would print an arbitrary row's unit over an incoherent number.
 * Per-type figures remain on the rows themselves.
 */
export function summarizeSpendTokens(rows: SpendByTaskType[]): SpendTokenTotals {
  const units = new Set(rows.map((r) => (r.unit || "").trim().toLowerCase()).filter(Boolean));
  if (units.size !== 1) return NO_TOKEN_TOTALS;

  const withAllocated = rows.filter((r) => r.allocated != null);
  const remainingPerRow = rows.map((r) => {
    if (r.remaining != null) return r.remaining;
    return r.allocated != null ? r.allocated - r.consumption : null;
  });
  const withRemaining = remainingPerRow.filter((r): r is number => r != null);
  return {
    unit: rows.find((r) => r.unit)?.unit ?? "",
    tokensUsed: rows.reduce((s, r) => s + (r.consumption ?? 0), 0),
    tokensAllocated: withAllocated.length
      ? withAllocated.reduce((s, r) => s + (r.allocated ?? 0), 0)
      : null,
    tokensRemaining: withRemaining.length ? withRemaining.reduce((s, r) => s + r, 0) : null,
  };
}

export function spendBarColor(pct: number): string {
  if (pct > 100) return USAGE_SPEND_DANGER;
  if (pct >= 90) return USAGE_SPEND_WARNING;
  return USAGE_SPEND_ACCENT;
}

export function tenantInitials(name: string): string {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((w) => w.length > 2 || /[A-Z]/.test(w[0] ?? ""));
  const letters = words.map((w) => w[0]).join("");
  return (letters || name).slice(0, 2).toUpperCase();
}

export function tenantAvatarBg(name: string): string {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.codePointAt(i) ?? 0;
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

/** Fixed color per task type (same identifier everywhere = same color), falling back to the rank cycle for unmapped types. */
export function taskTypeColor(taskType: string, index: number): string {
  const key = taskType.trim().toLowerCase() as TaskTypeColorKey;
  return METERING.COLORS.TASK_TYPE[key] ?? meteringColorAt(index);
}

/** Flat task list aggregated across tiers (quota from last tier write). */
export function aggregateTasks(breakdown: TenantTierBreakdown[]): AggregatedTaskUsage[] {
  const map = new Map<string, AggregatedTaskUsage>();
  const order: string[] = [];
  for (const tier of breakdown) {
    for (const t of tier.taskTypes ?? []) {
      const existing = map.get(t.taskType);
      if (!existing) {
        map.set(t.taskType, {
          taskType: t.taskType,
          unit: t.unit,
          quotaLimit: t.quotaLimit,
          consumed: t.consumed,
          remaining: t.remaining,
          spend: t.spend,
        });
        order.push(t.taskType);
      } else {
        existing.consumed += t.consumed;
        existing.spend += t.spend;
        existing.quotaLimit = t.quotaLimit;
        existing.remaining = t.remaining;
        existing.unit = t.unit || existing.unit;
      }
    }
  }
  return order.map((k) => map.get(k)!);
}

export function summaryFromDetail(detail: TenantUsageDetail): UsageSummaryResponse {
  const items = aggregateTasks(detail.tierBreakdown ?? []).map((i) => ({
    modelTaskType: i.taskType,
    unit: i.unit,
    consumption: i.consumed,
    allocated: i.quotaLimit ?? null,
    remaining: i.remaining ?? null,
    spend: i.spend,
    percentage: 0,
  }));
  const total = items.reduce((s, i) => s + i.spend, 0) || detail.spend;
  return {
    billingPeriod: "",
    totalSpend: total,
    currency: detail.currency,
    activeTenants: 1,
    budgetExceededTenants:
      detail.budget.remaining < 0 || detail.budget.percentageUsed > 100 ? 1 : 0,
    spendChangePercent: 0,
    spendByModelTaskType: items.map((i) => ({
      ...i,
      percentage: total > 0 ? Number(((i.spend / total) * 100).toFixed(1)) : 0,
    })),
  };
}

export function resolveSpendChangePercent(params: {
  isScoped: boolean;
  apiValue?: number;
  currentTotal?: number;
  prevTotal?: number;
  prevReady: boolean;
}): number | null {
  const { isScoped, apiValue, currentTotal, prevTotal, prevReady } = params;
  if (typeof apiValue === "number" && Number.isFinite(apiValue)) return apiValue;
  if (isScoped || !prevReady || currentTotal == null) return null;
  if (prevTotal == null || prevTotal <= 0) return currentTotal > 0 ? 100 : 0;
  return Number((((currentTotal - prevTotal) / prevTotal) * 100).toFixed(1));
}
