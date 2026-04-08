/**
 * Demo-only overlay for Usage dashboards. Preserves API tenant IDs for drill-down;
 * keeps real active_tenants count from the API.
 */
import type {
  AdopterUsageResponse,
  AdopterServiceUsageRow,
  AdopterTopTenantRow,
  TenantUsageDetailResponse,
  TenantServiceUsageRow,
} from "../services/usageService";

export const USAGE_DEMO_ENABLED = true;

export const DEMO_ADOPTER_COST_TOTAL = 124_856;
export const DEMO_TOP_TENANT_COSTS = [38_420, 43_218, 43_218] as const;
export const DEMO_TOP_TENANT_NAMES = ["tenant_corp_5", "Tenant_corp_3", "tenant_corp_6"] as const;

export const DEMO_TENANT_TOTAL_REQUESTS = 43_210;
export const DEMO_TENANT_PLAN_BUDGET = 50_000;
export const DEMO_TENANT_COST_USED = 38_420;
export const DEMO_TENANT_REMAINING = 11_580;
export const DEMO_TENANT_UTIL_PERCENT = 76;

/** Other top tenants — costs match admin “Top tenants” table */
const DEMO_TENANT_ALT_USED = 43_218;
const DEMO_TENANT_ALT_BUDGET = 56_000;
const DEMO_TENANT_ALT_REMAINING = DEMO_TENANT_ALT_BUDGET - DEMO_TENANT_ALT_USED;
const DEMO_TENANT_ALT_REQUESTS = Math.round(
  DEMO_TENANT_TOTAL_REQUESTS * (DEMO_TENANT_ALT_USED / DEMO_TENANT_COST_USED)
);
const DEMO_TENANT_ALT_UTIL = Math.round((100 * DEMO_TENANT_ALT_USED) / DEMO_TENANT_ALT_BUDGET);

export const DEMO_ACTIVE_SERVICES = 12;

/** NMT bar on adopter dashboard (~50% of limit) — scales with org cost narrative */
const DEMO_NMT_USED = 62_428;
const DEMO_NMT_LIMIT = 100_000;

function isNmtRow(name: string): boolean {
  return name.toLowerCase().includes("nmt");
}

function applyDemoTopTenants(rows: AdopterTopTenantRow[]): AdopterTopTenantRow[] {
  return DEMO_TOP_TENANT_NAMES.map((tenant_name, i) => {
    const existing = rows[i];
    return {
      tenant_id: existing?.tenant_id ?? `demo-tenant-${i}`,
      tenant_name,
      plan: existing?.plan?.trim() ? existing.plan : "Standard",
      cost: DEMO_TOP_TENANT_COSTS[i],
      status: "ACTIVE",
    };
  });
}

/** Twelve named services for the adopter “Service usage” panel */
const DEMO_ADOPTER_SERVICE_ROWS: AdopterServiceUsageRow[] = [
  { service_name: "NMT", unit_type: "units", used: DEMO_NMT_USED, limit: DEMO_NMT_LIMIT },
  { service_name: "ASR", unit_type: "minutes", used: 18_200, limit: 40_000 },
  { service_name: "TTS", unit_type: "characters", used: 12_400, limit: 35_000 },
  { service_name: "LLM", unit_type: "tokens", used: 9_800, limit: 50_000 },
  { service_name: "OCR", unit_type: "pages", used: 6_200, limit: 25_000 },
  { service_name: "Pipeline", unit_type: "jobs", used: 4_100, limit: 20_000 },
  { service_name: "Transliteration", unit_type: "units", used: 3_600, limit: 18_000 },
  { service_name: "NER", unit_type: "requests", used: 2_900, limit: 15_000 },
  { service_name: "Language detection", unit_type: "requests", used: 2_400, limit: 12_000 },
  { service_name: "Speaker diarization", unit_type: "minutes", used: 1_950, limit: 10_000 },
  { service_name: "PII guard", unit_type: "requests", used: 1_720, limit: 9_000 },
  { service_name: "Model routing", unit_type: "requests", used: 1_480, limit: 8_000 },
];

export function applyDemoAdopterUsage(data: AdopterUsageResponse): AdopterUsageResponse {
  if (!USAGE_DEMO_ENABLED) return data;
  const activeTenants = data.summary.active_tenants;
  const plan_breakdown =
    activeTenants === 3
      ? { premium: 1, standard: 1, basic: 1 }
      : data.summary.plan_breakdown;

  return {
    ...data,
    summary: {
      ...data.summary,
      active_tenants: activeTenants,
      plan_breakdown,
      total_requests_today: 128_493,
      requests_vs_yesterday_percent: 12.4,
      cost_consumed_this_month: DEMO_ADOPTER_COST_TOTAL,
      blocked_requests: {
        total: 2_847,
        quota_exceeded: 312,
        rate_limited: 2_535,
      },
    },
    service_usage: DEMO_ADOPTER_SERVICE_ROWS.map((row) => {
      const apiRow = (data.service_usage || []).find(
        (r) => r.service_name.toLowerCase() === row.service_name.toLowerCase()
      );
      if (apiRow && isNmtRow(row.service_name)) {
        return { ...row, unit_type: apiRow.unit_type || row.unit_type };
      }
      if (apiRow) {
        return { ...row, unit_type: apiRow.unit_type || row.unit_type };
      }
      return row;
    }),
    top_tenants: applyDemoTopTenants(data.top_tenants || []),
  };
}

function applyDemoTenantServiceUsage(totalUsed: number, walletUtilPercent: number): TenantServiceUsageRow[] {
  const nmtCost = Math.round(totalUsed * 0.58);
  const asrCost = Math.round(totalUsed * 0.22);
  const ttsCost = totalUsed - nmtCost - asrCost;
  const mk = (
    service_name: string,
    unit_type: string,
    total_cost: number,
    quota_percent: number
  ): TenantServiceUsageRow => {
    const quota_limit = 100_000;
    const units_used = Math.round((quota_limit * quota_percent) / 100);
    return {
      service_name,
      unit_type,
      units_used,
      quota_limit,
      quota_percent,
      rate_per_unit: Number((total_cost / Math.max(1, units_used)).toFixed(4)),
      total_cost,
    };
  };
  const nmtBar = Math.min(92, Math.max(55, walletUtilPercent + 2));
  return [
    mk("NMT", "units", nmtCost, nmtBar),
    mk("ASR", "minutes", asrCost, 44),
    mk("TTS", "characters", ttsCost, 38),
  ];
}

function resolveDemoTenantScenario(tenantName: string): {
  total_requests: number;
  total_plan_cost: number;
  total_used: number;
  remaining: number;
  utilization_percent: number;
} {
  const n = (tenantName || "").toLowerCase().replace(/\s+/g, "");
  if (n.includes("corp_3") || n.includes("corp3")) {
    return {
      total_requests: DEMO_TENANT_ALT_REQUESTS,
      total_plan_cost: DEMO_TENANT_ALT_BUDGET,
      total_used: DEMO_TENANT_ALT_USED,
      remaining: DEMO_TENANT_ALT_REMAINING,
      utilization_percent: DEMO_TENANT_ALT_UTIL,
    };
  }
  if (n.includes("corp_6") || n.includes("corp6")) {
    return {
      total_requests: DEMO_TENANT_ALT_REQUESTS,
      total_plan_cost: DEMO_TENANT_ALT_BUDGET,
      total_used: DEMO_TENANT_ALT_USED,
      remaining: DEMO_TENANT_ALT_REMAINING,
      utilization_percent: DEMO_TENANT_ALT_UTIL,
    };
  }
  return {
    total_requests: DEMO_TENANT_TOTAL_REQUESTS,
    total_plan_cost: DEMO_TENANT_PLAN_BUDGET,
    total_used: DEMO_TENANT_COST_USED,
    remaining: DEMO_TENANT_REMAINING,
    utilization_percent: DEMO_TENANT_UTIL_PERCENT,
  };
}

function splitIntTotal(total: number, n: number): number[] {
  if (n <= 0) return [];
  const base = Math.floor(total / n);
  const out = Array.from({ length: n }, () => base);
  out[n - 1] = total - base * (n - 1);
  return out;
}

export function applyDemoTenantUsage(data: TenantUsageDetailResponse): TenantUsageDetailResponse {
  if (!USAGE_DEMO_ENABLED) return data;
  const scenario = resolveDemoTenantScenario(data.tenant_name);
  const rawKeys = data.api_key_breakdown || [];
  const costs = splitIntTotal(scenario.total_used, Math.max(1, rawKeys.length));
  const reqs = splitIntTotal(scenario.total_requests, Math.max(1, rawKeys.length));
  const defaultKeyCosts = splitIntTotal(scenario.total_used, 3);
  const defaultKeyReqs = splitIntTotal(scenario.total_requests, 3);
  let keys =
    rawKeys.length > 0
      ? rawKeys.map((k, i) => ({
          ...k,
          requests: reqs[i] ?? reqs[reqs.length - 1],
          units_consumed: Math.round((reqs[i] ?? reqs[0]) * 12),
          total_cost: costs[i] ?? costs[costs.length - 1],
        }))
      : [
          {
            api_key_id: "demo-k1",
            api_key_masked: "sk-••••demo1",
            requests: defaultKeyReqs[0],
            units_consumed: Math.round(defaultKeyReqs[0] * 12),
            total_cost: defaultKeyCosts[0],
            last_used: new Date().toISOString(),
          },
          {
            api_key_id: "demo-k2",
            api_key_masked: "sk-••••demo2",
            requests: defaultKeyReqs[1],
            units_consumed: Math.round(defaultKeyReqs[1] * 12),
            total_cost: defaultKeyCosts[1],
            last_used: new Date().toISOString(),
          },
          {
            api_key_id: "demo-k3",
            api_key_masked: "sk-••••demo3",
            requests: defaultKeyReqs[2],
            units_consumed: Math.round(defaultKeyReqs[2] * 12),
            total_cost: defaultKeyCosts[2],
            last_used: new Date().toISOString(),
          },
        ];
  const kSum = keys.reduce((s, k) => s + k.total_cost, 0);
  if (keys.length && kSum !== scenario.total_used) {
    const adj = scenario.total_used - kSum;
    keys = keys.map((k, i) => (i === 0 ? { ...k, total_cost: k.total_cost + adj } : k));
  }

  return {
    ...data,
    status: "ACTIVE",
    total_requests: scenario.total_requests,
    wallet: {
      total_plan_cost: scenario.total_plan_cost,
      total_used: scenario.total_used,
      remaining: scenario.remaining,
      utilization_percent: scenario.utilization_percent,
    },
    service_usage: applyDemoTenantServiceUsage(scenario.total_used, scenario.utilization_percent),
    api_key_breakdown: keys,
  };
}
