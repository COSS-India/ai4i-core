import type { PlanPolicy } from "../services/policyService";

const TIER_ORDER = ["Tier-1", "Tier-2", "Tier-3"];

/** e.g. Tier-1 → "Tier-1 models" for plan / usage UI */
export function tierModelsLabel(tier: string | null | undefined): string {
  if (tier == null || String(tier).trim() === "") return "—";
  const raw = String(tier).trim();
  const x = raw.toLowerCase().replace(/_/g, "-");
  if (x === "tier-1" || x === "tier1") return "Tier-1 models";
  if (x === "tier-2" || x === "tier2") return "Tier-2 models";
  if (x === "tier-3" || x === "tier3") return "Tier-3 models";
  if (/^tier-/i.test(raw)) return `${raw.charAt(0).toUpperCase()}${raw.slice(1)} models`;
  return `${raw} models`;
}

export function sortTierLabels(tiers: string[]): string[] {
  const uniq = Array.from(new Set(tiers));
  return uniq.sort((a, b) => {
    const ia = TIER_ORDER.indexOf(a);
    const ib = TIER_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
  });
}

export type PlanNameGroup = {
  name: string;
  tierLabels: string;
  policies: PlanPolicy[];
};

/** Each plan is unique by tier; group by plan_name for display cards. */
export function groupPoliciesByName(policies: PlanPolicy[]): PlanNameGroup[] {
  const map = new Map<string, PlanPolicy[]>();
  for (const p of policies) {
    const k = p.plan_name || "Unknown";
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(p);
  }
  return Array.from(map.entries())
    .map(([name, items]) => {
      const tierLabels = sortTierLabels(items.map((i) => i.tier)).join(", ");
      const sorted = [...items].sort((a, b) => {
        const ia = TIER_ORDER.indexOf(a.tier);
        const ib = TIER_ORDER.indexOf(b.tier);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      });
      return { name, tierLabels, policies: sorted };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function formatQuotaSummary(p: PlanPolicy): string {
  const q = p.quota_config as Record<string, unknown> | undefined;
  if (!q) return "—";
  const rh = q.requests_per_hour;
  const sl = q.service_limits;
  if (typeof rh === "number") {
    const parts = [`${rh.toLocaleString()} req/hour`];
    if (Array.isArray(sl) && sl.length) {
      parts.push(`${sl.length} service limit(s)`);
    }
    return parts.join(", ");
  }
  return JSON.stringify(q);
}

export function formatRateSummary(p: PlanPolicy): string {
  const r = p.rate_limit_config as Record<string, unknown> | undefined;
  if (!r) return "—";
  const k = r.requests_per_hour_per_api_key;
  const t = r.requests_per_hour_per_tenant;
  if (typeof k === "number" && typeof t === "number") {
    return `${k} req/h API key, ${t} req/h tenant`;
  }
  return JSON.stringify(r);
}

export function formatServicesSummary(_p: PlanPolicy): string {
  return "Tier-scoped services (see tenant creation)";
}
